"""
AeroDataBox API client (via RapidAPI) — per-flight delay reason fallback.

Endpoint: https://aerodatabox.p.rapidapi.com/flights/iata/{ident}
Free tier via RapidAPI: ~500 requests/month.

Used as a fallback when AviationStack returns no delay reason code.
AeroDataBox sources delay reasons from OAG / airline operational data
and returns structured departure/arrival delay info.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from models import CauseBucket

logger = logging.getLogger(__name__)

_BASE = "https://aerodatabox.p.rapidapi.com/flights/iata/{ident}"

# AeroDataBox delayReason strings → CauseBucket
# The API returns plain-English strings, not IATA codes.
_REASON_KEYWORDS: list[tuple[list[str], "CauseBucket", str]] = [
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


async def fetch_delay_signal(
    flight_iata: str,
    api_key: str,
) -> AeroDataBoxSignal | None:
    """
    Fetch flight delay info from AeroDataBox via RapidAPI.
    Returns None if the key is blank, flight not found, or no useful data.
    """
    if not api_key.strip():
        return None

    url = _BASE.format(ident=flight_iata.upper())
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com",
    }

    async with httpx.AsyncClient(timeout=12) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            logger.warning("AeroDataBox fetch failed for %s: %s", flight_iata, exc)
            return None

    # AeroDataBox returns either a single object or a list; normalise to one record
    record: dict = body[0] if isinstance(body, list) and body else (body if isinstance(body, dict) else {})
    if not record:
        return None

    dep: dict = record.get("departure") or {}
    arr: dict = record.get("arrival") or {}

    dep_delay: int = _parse_delay(dep.get("delay") or dep.get("delayMinutes"))
    arr_delay: int = _parse_delay(arr.get("delay") or arr.get("delayMinutes"))

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


def _parse_delay(val: object) -> int:
    try:
        return max(0, int(float(str(val))))
    except (TypeError, ValueError):
        return 0


def _classify_reason(reason: str) -> tuple["CauseBucket | None", str]:
    """Match reason string against keyword groups. Returns (cause, label) or (None, '')."""
    if not reason:
        return None, ""
    for keywords, cause, label in _REASON_KEYWORDS:
        if any(kw in reason for kw in keywords):
            return cause, label
    return None, ""
