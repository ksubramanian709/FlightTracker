"""
OpenSky Network client — OAuth2 (required as of March 2026).

Free account at https://opensky-network.org provides:
  - /states/all?callsign=...    live position by callsign
  - /flights/arrival            ADS-B arrivals for an airport (single UTC day)
  - /flights/departure          ADS-B departures for an airport
  - /flights/aircraft           all legs for one ICAO24 transponder

When OPENSKY_CLIENT_ID / SECRET are not configured, returns empty results
so the rest of the app (mock flight adapter + FAA data) still works.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from config import settings
from models import TailLeg

logger = logging.getLogger(__name__)

_token_cache: dict[str, Any] = {}  # {"access_token": ..., "expires_at": float}


async def _get_access_token() -> str | None:
    if not settings.opensky_enabled:
        return None

    now = time.time()
    if _token_cache.get("access_token") and _token_cache.get("expires_at", 0) > now + 30:
        return _token_cache["access_token"]

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                settings.opensky_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.opensky_client_id,
                    "client_secret": settings.opensky_client_secret,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            _token_cache["access_token"] = payload["access_token"]
            _token_cache["expires_at"] = now + int(payload.get("expires_in", 3600))
            return _token_cache["access_token"]
        except Exception as exc:
            logger.warning("OpenSky token fetch failed: %s", exc)
            return None


async def _opensky_get(path: str, params: dict | None = None) -> list[dict] | dict | None:
    token = await _get_access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"{settings.opensky_base_url}{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.get(url, params=params or {}, headers=headers)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("OpenSky request failed [%s]: %s", path, exc)
            return None


def _day_window(date: datetime | None = None) -> tuple[int, int]:
    """Return (begin, end) as Unix timestamps covering the given UTC calendar day."""
    if date is None:
        date = datetime.now(timezone.utc)
    start = int(date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    end = int(date.replace(hour=23, minute=59, second=59, microsecond=0).timestamp())
    return start, end


def _flight_row_to_tail_leg(row: dict) -> TailLeg:
    """Convert one OpenSky flight row into a TailLeg."""
    def _ts(v: int | None) -> datetime | None:
        return datetime.fromtimestamp(v, tz=timezone.utc) if v else None

    dep = _ts(row.get("firstSeen") or row.get("departureTime"))
    arr = _ts(row.get("lastSeen") or row.get("arrivalTime"))

    return TailLeg(
        icao24=row.get("icao24", ""),
        callsign=(row.get("callsign") or "").strip(),
        origin=row.get("estDepartureAirport") or row.get("origin") or "UNKN",
        destination=row.get("estArrivalAirport") or row.get("destination") or "UNKN",
        actual_dep=dep,
        actual_arr=arr,
        status="completed" if arr else "in_flight",
    )


async def get_live_state(callsign: str) -> dict | None:
    """
    Get the current live state vector for a callsign.
    Returns the first matching state vector dict or None.
    """
    data = await _opensky_get("/states/all", {"callsign": callsign.upper().ljust(8)})
    if not data or not isinstance(data, dict):
        return None
    states = data.get("states") or []
    if not states:
        return None
    keys = [
        "icao24", "callsign", "origin_country", "time_position", "last_contact",
        "longitude", "latitude", "baro_altitude", "on_ground", "velocity",
        "true_track", "vertical_rate", "sensors", "geo_altitude", "squawk",
        "spi", "position_source",
    ]
    s = states[0]
    return dict(zip(keys, s)) if isinstance(s, list) else s


async def get_flights_by_aircraft(icao24: str, date: datetime | None = None) -> list[TailLeg]:
    """
    Return today's (or given date's) legs for an aircraft by ICAO24 hex.
    """
    begin, end = _day_window(date)
    data = await _opensky_get("/flights/aircraft", {"icao24": icao24.lower(), "begin": begin, "end": end})
    if not data or not isinstance(data, list):
        return []
    legs = [_flight_row_to_tail_leg(row) for row in data]
    legs.sort(key=lambda l: (l.actual_dep or datetime.min.replace(tzinfo=timezone.utc)))
    return legs


async def get_arrivals_for_airport(icao: str, date: datetime | None = None) -> list[dict]:
    """ADS-B arrivals at an airport on a given UTC day."""
    begin, end = _day_window(date)
    data = await _opensky_get("/flights/arrival", {"airport": icao.upper(), "begin": begin, "end": end})
    return data if isinstance(data, list) else []


async def get_departures_for_airport(icao: str, date: datetime | None = None) -> list[dict]:
    """ADS-B departures from an airport on a given UTC day."""
    begin, end = _day_window(date)
    data = await _opensky_get("/flights/departure", {"airport": icao.upper(), "begin": begin, "end": end})
    return data if isinstance(data, list) else []


async def resolve_icao24_from_callsign(callsign: str, date: datetime | None = None) -> str | None:
    """
    Try to find the ICAO24 for a callsign from today's live states first,
    then fall back to airport departure scans.
    """
    state = await get_live_state(callsign)
    if state:
        return state.get("icao24")
    return None
