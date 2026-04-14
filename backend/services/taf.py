"""
FAA Aviation Weather Center — TAF (Terminal Aerodrome Forecast) fetcher.

Endpoint: https://aviationweather.gov/api/data/taf
Free, unauthenticated. Returns structured forecast JSON.

Used to detect incoming weather that could cause delays:
- Low ceiling/visibility in the current or next forecast period
- Active precipitation or IFR/LIFR conditions in the TAF window
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_AWC_TAF_URL = "https://aviationweather.gov/api/data/taf"

_BAD_WX_KEYWORDS = [
    "ts", "ra", "sn", "fz", "fg", "br", "dz", "pl", "ic", "gr", "gs",
    "blsn", "+ra", "+sn", "tsra", "fzra",
]


def _is_bad_wx(wx_string: str | None) -> bool:
    if not wx_string:
        return False
    wx = wx_string.lower()
    return any(kw in wx for kw in _BAD_WX_KEYWORDS)


def _low_ceiling_or_vis(fcst: dict) -> bool:
    """Return True if this forecast period shows IFR/LIFR-equivalent conditions."""
    # Low visibility
    visib = fcst.get("visib") or ""
    try:
        vis_val = float(str(visib).replace("+", "").replace("SM", "").strip())
        if vis_val < 3:
            return True
    except (TypeError, ValueError):
        pass

    # Low ceiling
    sky = fcst.get("clouds") or fcst.get("sky") or []
    if isinstance(sky, list):
        for layer in sky:
            cover = (layer.get("cover") or "").upper()
            base = layer.get("base") or layer.get("cloudBase")
            if cover in ("BKN", "OVC", "VV") and base is not None:
                try:
                    if int(base) < 1000:
                        return True
                except (TypeError, ValueError):
                    pass

    return False


async def fetch_taf_signal(icao: str) -> dict | None:
    """
    Fetch TAF for the given ICAO airport. Returns a signal dict with:
      - has_bad_wx: bool
      - has_low_ceiling_or_vis: bool
      - description: str
      - raw_taf: str
    Returns None on error or if no TAF found.
    """
    icao = icao.upper()
    params = {
        "ids": icao,
        "format": "json",
        "metar": "false",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(_AWC_TAF_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("TAF fetch failed for %s: %s", icao, exc)
            return None

    if not data or not isinstance(data, list):
        return None

    taf = data[0]
    raw = taf.get("rawTAF") or taf.get("rawTaf") or ""

    # Find the forecast period covering now
    now_ts = datetime.now(timezone.utc).timestamp()
    fcsts = taf.get("fcsts") or []

    bad_wx = False
    low_cond = False
    descriptions: list[str] = []

    for fcst in fcsts:
        time_from = fcst.get("timeFrom") or 0
        time_to = fcst.get("timeTo") or 0
        # Cover the current period or the next 3 hours
        if time_from > now_ts + 10_800:
            continue

        wx = fcst.get("wxString") or fcst.get("wx") or ""
        if _is_bad_wx(wx):
            bad_wx = True
            descriptions.append(f"Forecast wx: {wx}")

        if _low_ceiling_or_vis(fcst):
            low_cond = True
            vis = fcst.get("visib", "")
            descriptions.append(f"Forecast visibility/ceiling below IFR minimums (vis={vis})")

    if not bad_wx and not low_cond:
        return None  # No relevant weather signal in TAF

    return {
        "has_bad_wx": bad_wx,
        "has_low_ceiling_or_vis": low_cond,
        "description": "; ".join(descriptions) or "Adverse weather in TAF",
        "raw_taf": raw,
    }
