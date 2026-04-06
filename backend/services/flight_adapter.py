"""
FlightAware AeroAPI v4 client.

Get a free key (500 calls/month) at:
  https://flightaware.com/aeroapi/portal

Set AEROAPI_KEY in backend/.env.

Queries used per analysis:
  GET /flights/{ident}                      → flight status, tail number, delay, inbound_fa_flight_id
  GET /flights/{inbound_fa_flight_id}       → previous leg to detect late inbound
  GET /flights/{registration}?ident_type=registration  → aircraft rotation history
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


def _delay_from_seconds(val: int | float | None) -> int:
    """Convert AeroAPI delay_seconds → minutes, floored at 0."""
    if not val:
        return 0
    return max(0, int(val / 60))


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
    Wraps the AeroAPI endpoints the delay engine needs.
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

        sched_dep = _dt(f.get("scheduled_out") or f.get("scheduled_off"))
        est_dep   = _dt(f.get("estimated_out") or f.get("actual_out") or f.get("actual_off"))
        sched_arr = _dt(f.get("scheduled_in") or f.get("scheduled_on"))
        est_arr   = _dt(f.get("estimated_in") or f.get("actual_in") or f.get("actual_on"))

        # AeroAPI provides departure_delay and arrival_delay directly in seconds
        dep_delay = _delay_from_seconds(f.get("departure_delay"))
        arr_delay = _delay_from_seconds(f.get("arrival_delay"))

        # Fall back to computing from timestamps if AeroAPI fields are 0
        if dep_delay == 0 and sched_dep and est_dep:
            dep_delay = _delay_minutes(sched_dep, est_dep)
        if arr_delay == 0 and sched_arr and est_arr:
            arr_delay = _delay_minutes(sched_arr, est_arr)

        return FlightStatus(
            flight_number=f.get("ident_iata") or f.get("ident") or "",
            airline=f.get("operator_iata") or f.get("operator") or "",
            tail_number=f.get("registration") or None,
            icao24=None,
            origin=dep.get("code_icao") or dep.get("code") or "",
            destination=arr.get("code_icao") or arr.get("code") or "",
            origin_iata=dep.get("code_iata") or dep.get("code") or "",
            destination_iata=arr.get("code_iata") or arr.get("code") or "",
            scheduled_dep=sched_dep,
            estimated_dep=est_dep,
            scheduled_arr=sched_arr,
            estimated_arr=est_arr,
            departure_delay_min=dep_delay,
            arrival_delay_min=arr_delay,
            status=_aeroapi_status_to_literal(f.get("status") or ""),
            inbound_fa_flight_id=f.get("inbound_fa_flight_id") or None,
            fa_flight_id=f.get("fa_flight_id") or None,
            data_source="aeroapi",
        )

    async def get_flight_status(
        self, flight_number: str, date: datetime | None = None
    ) -> FlightStatus | None:
        ident = _normalise(flight_number)
        params: dict = {"ident_type": "designator"}
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
        return self._parse_flight_row(flights[0])

    async def get_flight_by_fa_id(self, fa_flight_id: str) -> FlightStatus | None:
        """Fetch a specific flight by its fa_flight_id (used for inbound leg lookup)."""
        try:
            data = await self._get(f"/flights/{fa_flight_id}")
        except httpx.HTTPStatusError as exc:
            logger.warning("AeroAPI inbound lookup %s: %s", fa_flight_id, exc)
            return None
        except Exception as exc:
            logger.warning("AeroAPI inbound lookup %s: %s", fa_flight_id, exc)
            return None

        flights = data.get("flights") or []
        if not flights:
            return None
        return self._parse_flight_row(flights[0])

    # ------------------------------------------------------------------
    # Tail / aircraft rotation history
    # ------------------------------------------------------------------

    def _flight_to_tail_leg(self, f: dict) -> TailLeg:
        fs = self._parse_flight_row(f)
        # Normalise status to TailLeg's allowed literals
        raw_status = fs.status
        if raw_status in ("landed",):
            status_val: str = "completed"
        elif raw_status in ("active",):
            status_val = "in_flight"
        elif raw_status in ("scheduled",):
            status_val = "scheduled"
        elif raw_status == "cancelled":
            status_val = "cancelled"
        elif raw_status == "diverted":
            status_val = "cancelled"
        else:
            status_val = "unknown"

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
        Return all legs flown by a registration on the given date (or recent).
        Uses GET /flights/{registration}?ident_type=registration
        """
        params: dict = {"ident_type": "registration"}
        if date:
            params["start"] = date.strftime("%Y-%m-%dT00:00:00Z")
            params["end"]   = date.strftime("%Y-%m-%dT23:59:59Z")
        else:
            # Default: last 24 hours
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            params["start"] = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
            params["end"]   = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            data = await self._get(f"/flights/{tail.upper()}", params)
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
