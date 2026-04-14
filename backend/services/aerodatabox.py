"""
AeroDataBox API client (via RapidAPI) — per-flight delay reason fallback.

Endpoint: https://aerodatabox.p.rapidapi.com/flights/callsign/{callsign}
Free tier via RapidAPI: ~500 requests/month.

NOTE: AeroDataBox changed their API — the old /flights/iata/{ident} endpoint
no longer accepts 'iata' as a valid search type. The correct endpoint is now
/flights/callsign/{callsign}, where callsign is the ICAO airline code + flight
number (e.g. UA456 → UAL456).

Used as a fallback when AviationStack returns no delay reason code.
Delay is computed from scheduledTime vs revisedTime differences.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from models import CauseBucket

logger = logging.getLogger(__name__)

_BASE = "https://aerodatabox.p.rapidapi.com/flights/callsign/{callsign}"

# IATA airline code → ICAO callsign prefix
# Used to convert e.g. "UA456" → "UAL456"
_IATA_TO_ICAO_AIRLINE: dict[str, str] = {
    "AA": "AAL",  # American Airlines
    "AS": "ASA",  # Alaska Airlines
    "B6": "JBU",  # JetBlue
    "DL": "DAL",  # Delta
    "F9": "FFT",  # Frontier
    "G4": "AAY",  # Allegiant
    "HA": "HAL",  # Hawaiian
    "NK": "NKS",  # Spirit
    "UA": "UAL",  # United
    "WN": "SWA",  # Southwest
    "WS": "WJA",  # WestJet
    "AC": "ACA",  # Air Canada
    "BA": "BAW",  # British Airways
    "LH": "DLH",  # Lufthansa
    "AF": "AFR",  # Air France
    "KL": "KLM",  # KLM
    "EK": "UAE",  # Emirates
    "QR": "QTR",  # Qatar Airways
    "SQ": "SIA",  # Singapore Airlines
    "CX": "CPA",  # Cathay Pacific
    "JL": "JAL",  # Japan Airlines
    "NH": "ANA",  # All Nippon
    "QF": "QFA",  # Qantas
}

# AeroDataBox status strings → CauseBucket (used when no delayReason)
_STATUS_REASON_KEYWORDS: list[tuple[list[str], "CauseBucket", str]] = [
    (["weather", "wind", "storm", "fog", "snow", "ice", "thunder"], "weather", "weather conditions"),
    (["crew", "staff", "personnel", "cockpit", "cabin"], "carrier", "crew/staffing issue"),
    (["maintenance", "technical", "mechanical", "aircraft", "equipment"], "carrier", "maintenance/technical issue"),
    (["gate", "boarding", "fueling", "fuel", "catering", "loading", "baggage"], "carrier", "ground operations (gate/fueling/catering)"),
    (["late arriving", "late aircraft", "inbound", "previous flight", "rotation"], "late_inbound", "late arriving aircraft"),
    (["atc", "air traffic", "nas", "slot", "congestion", "reroute", "flow"], "airport_nas", "ATC/NAS restriction"),
    (["security", "customs", "immigration"], "carrier", "security/customs delay"),
]


@dataclass
class AeroDataBoxSignal:
    cause: "CauseBucket"
    detail: str
    weight: float
    dep_delay_min: int
    arr_delay_min: int


def _iata_to_callsign(flight_iata: str) -> str | None:
    """
    Convert IATA flight number like 'UA456' to AeroDataBox callsign 'UAL456'.
    Returns None if the airline prefix is not in the mapping.
    """
    flight = flight_iata.strip().upper()
    # Split on first digit
    for i, ch in enumerate(flight):
        if ch.isdigit():
            iata_code = flight[:i]
            number = flight[i:]
            icao_prefix = _IATA_TO_ICAO_AIRLINE.get(iata_code)
            if icao_prefix:
                return f"{icao_prefix}{number}"
            return None
    return None


def _parse_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # AeroDataBox format: "2026-04-12 14:05Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None


def _delay_minutes(scheduled: datetime | None, revised: datetime | None) -> int:
    """Return delay in minutes (positive = late, negative = early). Floored at 0."""
    if not scheduled or not revised:
        return 0
    diff = (revised - scheduled).total_seconds() / 60
    return max(0, int(diff))


async def fetch_delay_signal(
    flight_iata: str,
    api_key: str,
) -> AeroDataBoxSignal | None:
    """
    Fetch flight delay info from AeroDataBox via RapidAPI using the callsign endpoint.
    Returns None if the key is blank, callsign not mappable, flight not found,
    or no useful data.
    """
    if not api_key.strip():
        return None

    callsign = _iata_to_callsign(flight_iata)
    if not callsign:
        logger.debug("AeroDataBox: cannot map IATA %s to callsign — skipping", flight_iata)
        return None

    url = _BASE.format(callsign=callsign)
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com",
    }

    async with httpx.AsyncClient(timeout=12) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (404, 400):
                logger.debug("AeroDataBox: %s for callsign %s", resp.status_code, callsign)
                return None
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            logger.warning("AeroDataBox fetch failed for %s (%s): %s", flight_iata, callsign, exc)
            return None

    # AeroDataBox returns a list; take the first (most recent) result
    record: dict = body[0] if isinstance(body, list) and body else (body if isinstance(body, dict) else {})
    if not record:
        return None

    dep: dict = record.get("departure") or {}
    arr: dict = record.get("arrival") or {}

    # Compute delay from scheduled vs revised times
    dep_sched = _parse_utc((dep.get("scheduledTime") or {}).get("utc"))
    dep_revised = _parse_utc(
        (dep.get("revisedTime") or dep.get("runwayTime") or {}).get("utc")
    )
    arr_sched = _parse_utc((arr.get("scheduledTime") or {}).get("utc"))
    arr_revised = _parse_utc(
        (arr.get("revisedTime") or arr.get("runwayTime") or {}).get("utc")
    )

    dep_delay: int = _delay_minutes(dep_sched, dep_revised)
    arr_delay: int = _delay_minutes(arr_sched, arr_revised)

    # Try delay reason (not always present in the new API)
    raw_reason: str = (
        dep.get("delayReason")
        or dep.get("delay_reason")
        or record.get("delayReason")
        or ""
    ).strip().lower()

    cause, reason_label = _classify_reason(raw_reason)

    if not cause:
        if dep_delay > 15 or arr_delay > 15:
            return AeroDataBoxSignal(
                cause="operational_unknown",
                detail=f"AeroDataBox: {dep_delay}min dep delay, reason unclassified",
                weight=0.35,
                dep_delay_min=dep_delay,
                arr_delay_min=arr_delay,
            )
        return None

    delay_str = f"{dep_delay}min dep" if dep_delay else f"{arr_delay}min arr"
    detail = f"AeroDataBox delay reason: {reason_label} ({delay_str} delay)"
    confirmed_delay = max(dep_delay, arr_delay)
    weight = 0.75 if confirmed_delay >= 15 else 0.55

    return AeroDataBoxSignal(
        cause=cause,
        detail=detail,
        weight=weight,
        dep_delay_min=dep_delay,
        arr_delay_min=arr_delay,
    )


def _classify_reason(reason: str) -> tuple["CauseBucket | None", str]:
    """Match reason string against keyword groups. Returns (cause, label) or (None, '')."""
    if not reason:
        return None, ""
    for keywords, cause, label in _STATUS_REASON_KEYWORDS:
        if any(kw in reason for kw in keywords):
            return cause, label
    return None, ""
