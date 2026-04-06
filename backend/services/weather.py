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


_WTTR_URL = "https://wttr.in/{location}?format=j1"

# Weather code → friendly condition string (wttr.in / WorldWeatherOnline codes)
_WTTR_CODES: dict[int, str] = {
    113: "Clear",
    116: "Partly Cloudy",
    119: "Cloudy",
    122: "Overcast",
    143: "Mist",
    176: "Light Rain Showers",
    179: "Light Snow Showers",
    182: "Sleet",
    185: "Light Freezing Drizzle",
    200: "Thunderstorm",
    227: "Blowing Snow",
    230: "Blizzard",
    248: "Fog",
    260: "Freezing Fog",
    263: "Light Drizzle",
    266: "Light Drizzle",
    281: "Freezing Drizzle",
    284: "Heavy Freezing Drizzle",
    293: "Light Rain",
    296: "Light Rain",
    299: "Moderate Rain",
    302: "Moderate Rain",
    305: "Heavy Rain",
    308: "Heavy Rain",
    311: "Light Freezing Rain",
    314: "Moderate Freezing Rain",
    317: "Light Sleet",
    320: "Moderate Sleet",
    323: "Light Snow",
    326: "Light Snow",
    329: "Moderate Snow",
    332: "Heavy Snow",
    335: "Heavy Snow",
    338: "Heavy Snow",
    350: "Ice Pellets",
    353: "Light Rain Showers",
    356: "Moderate Rain Showers",
    359: "Heavy Rain Showers",
    362: "Light Sleet Showers",
    365: "Moderate Sleet Showers",
    368: "Light Snow Showers",
    371: "Moderate Snow Showers",
    374: "Light Ice Pellet Showers",
    377: "Moderate Ice Pellet Showers",
    386: "Thunderstorm with Rain",
    389: "Heavy Thunderstorm with Rain",
    392: "Thunderstorm with Snow",
    395: "Heavy Blizzard",
}


def _wttr_flight_category(vis_km: float) -> str:
    """Estimate ICAO flight category from visibility in km."""
    vis_sm = vis_km * 0.621371
    if vis_sm >= 5:
        return "VFR"
    if vis_sm >= 3:
        return "MVFR"
    if vis_sm >= 1:
        return "IFR"
    return "LIFR"


async def fetch_wttr_fallback(iata_or_city: str) -> METARWeather | None:
    """
    Fallback weather via wttr.in (WorldWeatherOnline) for airports where
    the FAA Aviation Weather Center has no METAR (e.g. international airports).
    Accepts IATA code or city name.
    """
    url = _WTTR_URL.format(location=iata_or_city.upper())
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("wttr.in fallback failed for %s: %s", iata_or_city, exc)
            return None

    try:
        cur = data["current_condition"][0]
    except (KeyError, IndexError):
        return None

    temp_c_raw = cur.get("temp_C")
    temp_f_raw = cur.get("temp_F")
    humidity_raw = cur.get("humidity")
    wind_kmph = cur.get("windspeedKmph")
    wind_deg = cur.get("winddirDegree")
    wind_16pt = cur.get("winddir16Point", "")
    vis_km_raw = cur.get("visibility")
    pressure_raw = cur.get("pressure")
    wx_code_raw = cur.get("weatherCode")
    wx_desc_list = cur.get("weatherDesc", [])

    try:
        temp_c: float | None = round(float(temp_c_raw), 1)
    except (TypeError, ValueError):
        temp_c = None

    try:
        temp_f: float | None = round(float(temp_f_raw), 1)
    except (TypeError, ValueError):
        temp_f = _c_to_f(temp_c)

    try:
        humidity_pct: int | None = int(humidity_raw)
    except (TypeError, ValueError):
        humidity_pct = None

    # km/h → knots (1 kt = 1.852 km/h)
    try:
        wind_kt: int | None = round(float(wind_kmph) / 1.852)
    except (TypeError, ValueError):
        wind_kt = None

    try:
        wind_direction: int | None = int(wind_deg)
    except (TypeError, ValueError):
        wind_direction = None

    wind_dir_label = f"{wind_16pt} ({wind_direction}°)" if wind_16pt and wind_direction is not None else wind_16pt

    try:
        vis_km = float(vis_km_raw)
        vis_sm_val = vis_km * 0.621371
        vis_str = f"{vis_sm_val:.0f} SM" if vis_sm_val < 10 else "10+ SM"
        flight_cat = _wttr_flight_category(vis_km)
    except (TypeError, ValueError):
        vis_str = ""
        vis_km = 10.0
        flight_cat = "VFR"

    # hPa → inHg (1 hPa = 0.02953 inHg)
    try:
        altim: float | None = round(float(pressure_raw) * 0.02953, 2)
    except (TypeError, ValueError):
        altim = None

    try:
        wx_code = int(wx_code_raw)
        conditions_friendly = _WTTR_CODES.get(wx_code, "")
    except (TypeError, ValueError):
        conditions_friendly = ""

    if not conditions_friendly and wx_desc_list:
        conditions_friendly = wx_desc_list[0].get("value", "")

    return METARWeather(
        temp_c=temp_c,
        temp_f=temp_f,
        humidity_pct=humidity_pct,
        wind_direction=wind_direction,
        wind_direction_label=wind_dir_label,
        wind_speed_kt=wind_kt,
        visibility_sm=vis_str,
        conditions_friendly=conditions_friendly,
        altimeter_inhg=altim,
        flight_category=flight_cat,
    )


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
