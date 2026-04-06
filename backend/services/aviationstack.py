"""
AviationStack API client — per-flight delay reason codes.

Endpoint: http://api.aviationstack.com/v1/flights
Free tier: 500 calls/month, HTTP only (HTTPS requires paid plan).

Returns airline-reported IATA delay reason codes:
  A = Airline / Carrier (crew, mechanical, gate, fueling)
  B = Weather
  C = NAS / ATC (en-route congestion, ATC reroutes, EDCT)
  D = Security
  E = Late arriving aircraft

These come from the airline's own ACARS data — far more specific than
the FAA NAS Status API which only reflects system-wide ground programs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from models import CauseBucket

logger = logging.getLogger(__name__)

_BASE = "http://api.aviationstack.com/v1/flights"

# AviationStack delay reason code → CauseBucket
_REASON_MAP: dict[str, "CauseBucket"] = {
    "A": "carrier",          # Airline/Carrier
    "B": "weather",          # Weather
    "C": "airport_nas",      # NAS / ATC
    "D": "carrier",          # Security (rare; treat as carrier-side)
    "E": "late_inbound",     # Late arriving aircraft
}

_REASON_LABELS: dict[str, str] = {
    "A": "airline/carrier (crew, maintenance, or gate)",
    "B": "weather",
    "C": "NAS/ATC restriction",
    "D": "security procedure",
    "E": "late arriving aircraft",
}


@dataclass
class AviationStackSignal:
    cause: "CauseBucket"
    detail: str
    weight: float
    dep_delay_min: int
    arr_delay_min: int


async def fetch_delay_signal(
    flight_iata: str,
    api_key: str,
) -> AviationStackSignal | None:
    """
    Fetch the most recent matching flight from AviationStack and extract
    delay reason. Returns None if the key is blank, the flight is not found,
    or no delay reason is available.
    """
    if not api_key.strip():
        return None

    params = {
        "access_key": api_key,
        "flight_iata": flight_iata.upper(),
        "limit": "1",
    }

    async with httpx.AsyncClient(timeout=12) as client:
        try:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            logger.warning("AviationStack fetch failed for %s: %s", flight_iata, exc)
            return None

    data: list[dict] = (body.get("data") or [])
    if not data:
        logger.debug("AviationStack: no data for %s", flight_iata)
        return None

    flight = data[0]
    dep: dict = flight.get("departure") or {}
    arr: dict = flight.get("arrival") or {}

    dep_delay: int = int(dep.get("delay") or 0)
    arr_delay: int = int(arr.get("delay") or 0)

    # AviationStack exposes delay_reason as a string or single-letter code
    raw_reason: str = (
        dep.get("delay_reason")
        or flight.get("delay_reason")
        or ""
    ).strip().upper()

    # Normalise: some responses return full words like "CARRIER" or "WEATHER"
    reason_code = _normalise_reason(raw_reason)

    if not reason_code:
        # No reason code, but we still have the delay amounts — return a weak
        # signal so the engine knows this flight is confirmed delayed.
        if dep_delay > 15 or arr_delay > 15:
            return AviationStackSignal(
                cause="operational_unknown",
                detail=f"AviationStack: {dep_delay}min dep delay, no reason code reported",
                weight=0.40,
                dep_delay_min=dep_delay,
                arr_delay_min=arr_delay,
            )
        return None

    cause = _REASON_MAP.get(reason_code, "operational_unknown")
    label = _REASON_LABELS.get(reason_code, reason_code)
    delay_str = f"{dep_delay}min dep" if dep_delay else f"{arr_delay}min arr"
    detail = f"AviationStack delay reason: {label} ({delay_str} delay)"

    # Higher weight when the delay is confirmed significant
    confirmed_delay = max(dep_delay, arr_delay)
    weight = 0.85 if confirmed_delay >= 15 else 0.65

    return AviationStackSignal(
        cause=cause,
        detail=detail,
        weight=weight,
        dep_delay_min=dep_delay,
        arr_delay_min=arr_delay,
    )


def _normalise_reason(raw: str) -> str:
    """Map verbose strings → single-letter code. Return '' if unrecognised."""
    if not raw:
        return ""
    # Already a single letter
    if raw in _REASON_MAP:
        return raw
    # Verbose forms from some AviationStack responses
    _VERBOSE: dict[str, str] = {
        "CARRIER": "A",
        "AIRLINE": "A",
        "WEATHER": "B",
        "NAS": "C",
        "ATC": "C",
        "NATIONAL AVIATION SYSTEM": "C",
        "SECURITY": "D",
        "LATE AIRCRAFT": "E",
        "LATE ARRIVING AIRCRAFT": "E",
    }
    return _VERBOSE.get(raw, "")
