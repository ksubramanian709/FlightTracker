"""
FlightAware AeroAPI v4 client.

Get a free key (500 calls/month) at:
  https://flightaware.com/aeroapi/portal

Set AEROAPI_KEY in backend/.env.

Two queries per analysis:
  GET /flights/{ident}             → flight status, tail number, delay
  GET /aircraft/{tail}/flights     → same-aircraft rotation history

The app raises on startup if AEROAPI_KEY is missing so the error is obvious.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from config import settings
from models import FlightStatus, TailLeg

logger = logging.getLogger(__name__)


def _normalise(flight: str) -> str:
    """Strip spaces and uppercase: 'UA 456' → 'UA456'."""
    return re.sub(r"\s+", "", flight.upper())


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _delay_minutes(scheduled: datetime | None, actual: datetime | None) -> int:
    if not scheduled or not actual:
        return 0
    return max(0, int((actual - scheduled).total_seconds() / 60))


def _aeroapi_status_to_literal(raw: str) -> str:
    mapping = {
        "scheduled": "scheduled",
        "filed": "scheduled",
        "active": "active",
        "en route": "active",
        "landed": "landed",
        "arrived": "landed",
        "cancelled": "cancelled",
        "diverted": "diverted",
    }
    return mapping.get(raw.lower().strip(), "unknown")


class AeroAPIClient:
    """
    Wraps the two AeroAPI endpoints the delay engine needs.
    One shared httpx.AsyncClient is created per request context.
    """

    def __init__(self) -> None:
        if not settings.aeroapi_key:
            raise RuntimeError(
                "AEROAPI_KEY is not set. Get a free key at "
                "https://flightaware.com/aeroapi/portal and add it to backend/.env"
            )
        self._base = settings.aeroapi_base_url.rstrip("/")
        self._headers = {
            "x-apikey": settings.aeroapi_key,
            "Accept": "application/json; charset=UTF-8",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=self._headers, params=params or {})
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Flight status
    # ------------------------------------------------------------------

    def _parse_flight_row(self, f: dict) -> FlightStatus:
        dep = f.get("origin") or {}
        arr = f.get("destination") or {}

        sched_dep = _dt(f.get("scheduled_out") or f.get("filed_departuretime"))
        est_dep   = _dt(f.get("actual_out") or f.get("estimated_out") or f.get("actual_off"))
        sched_arr = _dt(f.get("scheduled_in") or f.get("filed_arrivaltime"))
        est_arr   = _dt(f.get("actual_in") or f.get("estimated_in") or f.get("actual_on"))

        return FlightStatus(
            flight_number=f.get("ident_iata") or f.get("ident") or "",
            airline=f.get("operator_iata") or f.get("operator") or "",
            tail_number=f.get("registration") or None,
            icao24=None,          # enriched later via OpenSky if needed
            origin=dep.get("code_icao") or dep.get("code") or "",
            destination=arr.get("code_icao") or arr.get("code") or "",
            origin_iata=dep.get("code_iata") or dep.get("code") or "",
            destination_iata=arr.get("code_iata") or arr.get("code") or "",
            scheduled_dep=sched_dep,
            estimated_dep=est_dep,
            scheduled_arr=sched_arr,
            estimated_arr=est_arr,
            departure_delay_min=_delay_minutes(sched_dep, est_dep),
            arrival_delay_min=_delay_minutes(sched_arr, est_arr),
            status=_aeroapi_status_to_literal(f.get("status") or ""),
            data_source="aeroapi",
        )

    async def get_flight_status(
        self, flight_number: str, date: datetime | None = None
    ) -> FlightStatus | None:
        """
        Fetch the most relevant flight for the given identifier and optional date.
        Returns the most recent matching flight, or None if not found.
        """
        ident = _normalise(flight_number)
        params: dict = {}
        if date:
            params["start"] = date.strftime("%Y-%m-%dT00:00:00Z")
            params["end"]   = date.strftime("%Y-%m-%dT23:59:59Z")

        try:
            data = await self._get(f"/flights/{ident}", params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.error("AeroAPI flight-status %s: %s", ident, exc)
            return None
        except Exception as exc:
            logger.error("AeroAPI flight-status %s: %s", ident, exc)
            return None

        flights = data.get("flights") or []
        if not flights:
            return None
        # Pick the most recent (last in list) — AeroAPI returns newest first
        return self._parse_flight_row(flights[0])

    # ------------------------------------------------------------------
    # Tail / aircraft rotation history
    # ------------------------------------------------------------------

    def _flight_to_tail_leg(self, f: dict) -> TailLeg:
        fs = self._parse_flight_row(f)
        status_val = fs.status if fs.status in (
            "completed", "in_flight", "scheduled", "cancelled", "diverted"
        ) else "unknown"
        # AeroAPI uses "landed" — map to "completed"
        if status_val == "landed":
            status_val = "completed"
        return TailLeg(
            icao24="",
            callsign=fs.flight_number,
            origin=fs.origin,
            destination=fs.destination,
            scheduled_dep=fs.scheduled_dep,
            actual_dep=fs.estimated_dep,
            scheduled_arr=fs.scheduled_arr,
            actual_arr=fs.estimated_arr,
            departure_delay_min=fs.departure_delay_min,
            arrival_delay_min=fs.arrival_delay_min,
            status=status_val,
        )

    async def get_tail_history(
        self, tail: str, date: datetime | None = None
    ) -> list[TailLeg]:
        """
        Return all legs flown by a tail number on the given date (or today).
        Sorted by actual departure time ascending.
        """
        params: dict = {}
        if date:
            params["start"] = date.strftime("%Y-%m-%dT00:00:00Z")
            params["end"]   = date.strftime("%Y-%m-%dT23:59:59Z")

        try:
            data = await self._get(f"/aircraft/{tail.upper()}/flights", params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            logger.error("AeroAPI tail-history %s: %s", tail, exc)
            return []
        except Exception as exc:
            logger.error("AeroAPI tail-history %s: %s", tail, exc)
            return []

        flights = data.get("flights") or []
        legs = [self._flight_to_tail_leg(f) for f in flights]
        legs.sort(key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc))
        return legs


def get_client() -> AeroAPIClient:
    """Dependency-injectable factory used by routers."""
    return AeroAPIClient()
