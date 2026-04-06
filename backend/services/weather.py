"""
FAA Aviation Weather Center — METAR fetcher.

Endpoint: https://aviationweather.gov/api/data/metar
Free, unauthenticated, returns decoded METAR JSON.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from models import METARWeather

logger = logging.getLogger(__name__)

_AWC_URL = "https://aviationweather.gov/api/data/metar"

# wx code → friendly string
_WX_CODES: dict[str, str] = {
    "+TSRA": "Heavy Thunderstorm & Rain",
    "TSRA":  "Thunderstorm & Rain",
    "-TSRA": "Light Thunderstorm & Rain",
    "TS":    "Thunderstorm",
    "+RA":   "Heavy Rain",
    "RA":    "Rain",
    "-RA":   "Light Rain",
    "+SN":   "Heavy Snow",
    "SN":    "Snow",
    "-SN":   "Light Snow",
    "FZRA":  "Freezing Rain",
    "-FZRA": "Light Freezing Rain",
    "FZDZ":  "Freezing Drizzle",
    "+DZ":   "Heavy Drizzle",
    "DZ":    "Drizzle",
    "-DZ":   "Light Drizzle",
    "FG":    "Fog",
    "MIFG":  "Shallow Fog",
    "BCFG":  "Patchy Fog",
    "BR":    "Mist",
    "HZ":    "Haze",
    "FU":    "Smoke",
    "DU":    "Dust",
    "SA":    "Sand",
    "IC":    "Ice Crystals",
    "GR":    "Hail",
    "GS":    "Small Hail",
    "SG":    "Snow Grains",
    "PL":    "Ice Pellets",
    "+PL":   "Heavy Ice Pellets",
    "BLSN":  "Blowing Snow",
    "BLDU":  "Blowing Dust",
    "VCSH":  "Showers Nearby",
    "SHRA":  "Rain Showers",
    "-SHRA": "Light Rain Showers",
    "SHSN":  "Snow Showers",
}

_CLOUD_FRIENDLY: dict[str, str] = {
    "SKC": "Clear skies",
    "CLR": "Clear skies",
    "CAVOK": "Clear skies",
    "FEW": "Few clouds",
    "SCT": "Scattered clouds",
    "BKN": "Broken clouds",
    "OVC": "Overcast",
    "VV":  "Vertical visibility (obscured)",
}

_CATEGORY_LABEL: dict[str, str] = {
    "VFR":  "VFR",
    "MVFR": "MVFR",
    "IFR":  "IFR",
    "LIFR": "LIFR",
}


def _c_to_f(c: float | None) -> float | None:
    if c is None:
        return None
    return round(c * 9 / 5 + 32, 1)


def _wind_direction_label(wdir: Any) -> str:
    if isinstance(wdir, str) and wdir.upper() == "VRB":
        return "Variable"
    try:
        deg = int(wdir)
    except (TypeError, ValueError):
        return str(wdir) if wdir else ""
    # cardinal compass
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    idx = round(deg / 22.5) % 16
    return f"{dirs[idx]} ({deg}°)"


def _friendly_wx(wx_string: str | None) -> str:
    if not wx_string:
        return ""
    # May have multiple codes separated by spaces
    parts = wx_string.strip().split()
    labels = [_WX_CODES.get(p, p) for p in parts]
    return ", ".join(labels)


def _sky_summary(clouds: list[dict]) -> str:
    if not clouds:
        return ""
    parts: list[str] = []
    for c in clouds:
        cover = c.get("cover", "")
        base = c.get("base")
        label = _CLOUD_FRIENDLY.get(cover, cover)
        if base is not None:
            parts.append(f"{label} at {base:,} ft")
        else:
            parts.append(label)
    return "; ".join(parts)


def _humidity(temp_c: float | None, dewp_c: float | None) -> int | None:
    """Magnus formula approximation."""
    if temp_c is None or dewp_c is None:
        return None
    import math
    a, b = 17.625, 243.04
    rh = 100 * math.exp(a * dewp_c / (b + dewp_c)) / math.exp(a * temp_c / (b + temp_c))
    return round(rh)


async def fetch_metar(icao: str) -> METARWeather | None:
    """Fetch latest METAR for an airport and return a structured METARWeather object."""
    icao = icao.upper()
    params = {
        "ids": icao,
        "format": "json",
        "taf": "false",
        "hours": "3",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(_AWC_URL, params=params)
            resp.raise_for_status()
            data: list[dict] = resp.json()
        except Exception as exc:
            logger.warning("METAR fetch failed for %s: %s", icao, exc)
            return None

    if not data:
        return None

    m = data[0]  # most recent observation

    temp_c: float | None = m.get("temp")
    dewp_c: float | None = m.get("dewp")
    wdir = m.get("wdir")
    wspd: int | None = m.get("wspd")
    wgst: int | None = m.get("wgst")
    visib = m.get("visib")
    altim: float | None = m.get("altim")
    wx_string: str | None = m.get("wxString")
    clouds_raw: list[dict] = m.get("clouds") or []
    raw_ob: str = m.get("rawOb") or ""
    flight_cat: str = m.get("flightCategory") or ""

    temp_f = _c_to_f(temp_c)
    humidity = _humidity(temp_c, dewp_c)
    wind_dir_label = _wind_direction_label(wdir)
    conditions_friendly = _friendly_wx(wx_string)
    sky_summary = _sky_summary(clouds_raw)

    # Visibility can be numeric or "10+" string
    vis_str = ""
    try:
        vis_val = float(str(visib).replace("+", ""))
        vis_str = f"{vis_val} SM" if vis_val < 10 else "10+ SM"
    except (TypeError, ValueError):
        vis_str = str(visib) if visib else ""

    return METARWeather(
        temp_c=round(temp_c, 1) if temp_c is not None else None,
        temp_f=temp_f,
        dewpoint_c=round(dewp_c, 1) if dewp_c is not None else None,
        humidity_pct=humidity,
        wind_direction=int(wdir) if isinstance(wdir, (int, float)) else None,
        wind_direction_label=wind_dir_label,
        wind_speed_kt=int(wspd) if wspd is not None else None,
        wind_gust_kt=int(wgst) if wgst is not None else None,
        visibility_sm=vis_str,
        conditions=wx_string or "",
        conditions_friendly=conditions_friendly,
        sky_summary=sky_summary,
        altimeter_inhg=round(altim, 2) if altim else None,
        raw_metar=raw_ob,
        flight_category=flight_cat,
        clouds=[{"cover": c.get("cover", ""), "base": c.get("base")} for c in clouds_raw],
    )
