"""
FAA data clients:

1. NAS Status (nasstatus.faa.gov) — live airport delay programs, XML, no auth.
2. ASWS (soa.smext.faa.gov) — per-airport weather + status, JSON, no auth.

Both are unauthenticated and free. NAS refreshes roughly every 3-5 minutes.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
import xmltodict

from config import settings
from models import AirportCondition, DelayProgram, METARWeather
from services.weather import fetch_metar, fetch_wttr_fallback

logger = logging.getLogger(__name__)

# ICAO→IATA mappings for the most common US / international hubs
_ICAO_TO_IATA: dict[str, tuple[str, str]] = {
    "KATL": ("ATL", "Atlanta Hartsfield-Jackson"),
    "KLAX": ("LAX", "Los Angeles International"),
    "KORD": ("ORD", "Chicago O'Hare"),
    "KDFW": ("DFW", "Dallas/Fort Worth"),
    "KJFK": ("JFK", "New York JFK"),
    "KLGA": ("LGA", "New York LaGuardia"),
    "KEWR": ("EWR", "Newark Liberty"),
    "KSFO": ("SFO", "San Francisco International"),
    "KDEN": ("DEN", "Denver International"),
    "KLAS": ("LAS", "Las Vegas Harry Reid"),
    "KPHX": ("PHX", "Phoenix Sky Harbor"),
    "KSEA": ("SEA", "Seattle-Tacoma"),
    "KMCO": ("MCO", "Orlando International"),
    "KMIA": ("MIA", "Miami International"),
    "KBOS": ("BOS", "Boston Logan"),
    "KCLT": ("CLT", "Charlotte Douglas"),
    "KIAD": ("IAD", "Washington Dulles"),
    "KDCA": ("DCA", "Washington Reagan"),
    "KBWI": ("BWI", "Baltimore/Washington"),
    "KIAH": ("IAH", "Houston George Bush"),
    "KHOU": ("HOU", "Houston Hobby"),
    "KMSP": ("MSP", "Minneapolis-Saint Paul"),
    "KDTW": ("DTW", "Detroit Metropolitan"),
    "KPHL": ("PHL", "Philadelphia International"),
    "KSALT": ("SLC", "Salt Lake City International"),
    "KSLC": ("SLC", "Salt Lake City International"),
    "KPDX": ("PDX", "Portland International"),
    "KSAN": ("SAN", "San Diego International"),
    "KFLL": ("FLL", "Fort Lauderdale"),
    "KTPA": ("TPA", "Tampa International"),
    "KBNA": ("BNA", "Nashville International"),
    "KAUS": ("AUS", "Austin-Bergstrom"),
    "KSTL": ("STL", "St. Louis Lambert"),
    "KMEM": ("MEM", "Memphis International"),
    "KPIT": ("PIT", "Pittsburgh International"),
    "KCLE": ("CLE", "Cleveland Hopkins"),
    "KCVG": ("CVG", "Cincinnati/Northern Kentucky"),
    "KIND": ("IND", "Indianapolis International"),
    "KMKE": ("MKE", "Milwaukee Mitchell"),
    "KMDW": ("MDW", "Chicago Midway"),
    "KRDU": ("RDU", "Raleigh-Durham"),
    "KSDF": ("SDF", "Louisville Muhammad Ali"),
    "KCHS": ("CHS", "Charleston International"),
    "KRIC": ("RIC", "Richmond International"),
    "KNORFOLK": ("ORF", "Norfolk International"),
    "KORF": ("ORF", "Norfolk International"),
    "KELP": ("ELP", "El Paso International"),
    "KABQ": ("ABQ", "Albuquerque International"),
    "KOKC": ("OKC", "Oklahoma City Will Rogers"),
    "KTUL": ("TUL", "Tulsa International"),
    "KBHM": ("BHM", "Birmingham-Shuttlesworth"),
    "KMSY": ("MSY", "New Orleans Louis Armstrong"),
    "KJAX": ("JAX", "Jacksonville International"),
    "KRSW": ("RSW", "Southwest Florida"),
    "KPBI": ("PBI", "Palm Beach International"),
    "KSAT": ("SAT", "San Antonio International"),
    # International (ICAO → IATA)
    "EGLL": ("LHR", "London Heathrow"),
    "LFPG": ("CDG", "Paris Charles de Gaulle"),
    "EDDF": ("FRA", "Frankfurt Airport"),
    "OMDB": ("DXB", "Dubai International"),
    "VHHH": ("HKG", "Hong Kong International"),
    "RJTT": ("HND", "Tokyo Haneda"),
    "YSSY": ("SYD", "Sydney Kingsford Smith"),
    "CYYZ": ("YYZ", "Toronto Pearson"),
    "MMMX": ("MEX", "Mexico City International"),
}

# IATA → ICAO reverse lookup
_IATA_TO_ICAO: dict[str, str] = {v[0]: k for k, v in _ICAO_TO_IATA.items()}


def iata_to_icao(iata: str) -> str:
    """Convert IATA code to ICAO. For US airports without a mapping, prepend K."""
    iata = iata.upper()
    if iata in _IATA_TO_ICAO:
        return _IATA_TO_ICAO[iata]
    if len(iata) == 3:
        return f"K{iata}"
    return iata


def icao_to_iata(icao: str) -> str:
    icao = icao.upper()
    return _ICAO_TO_IATA.get(icao, ("", ""))[0] or icao.lstrip("K")


def _airport_name(icao: str) -> str:
    return _ICAO_TO_IATA.get(icao.upper(), ("", icao))[1]


def _normalize_icao(code: str) -> str:
    """Accept IATA (3-letter) or ICAO (4-letter) and always return ICAO."""
    code = code.strip().upper()
    if len(code) == 3:
        return iata_to_icao(code)
    return code


async def fetch_faa_nas_all() -> dict[str, Any]:
    """
    Fetch the full NAS status XML and return a dict keyed by ICAO airport code.
    Uses xmltodict for parsing. Returns {} on error.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(settings.faa_nas_url, headers={"Accept": "application/xml"})
            resp.raise_for_status()
            data = xmltodict.parse(resp.text, force_list=("Delay", "Closure", "Program"))
            return data
        except Exception as exc:
            logger.warning("FAA NAS fetch failed: %s", exc)
            return {}


def _extract_programs_for_airport(nas_data: dict, icao: str) -> list[DelayProgram]:
    """Walk the NAS XML structure and extract active delay programs for one airport."""
    programs: list[DelayProgram] = []
    try:
        delays = nas_data.get("AIRPORT_STATUS_INFORMATION", {}).get("Delay", []) or []
        for delay_block in delays:
            airport_info = delay_block.get("ARPT", "")
            if icao.upper() not in str(airport_info).upper():
                continue
            programs_raw = delay_block.get("Program", []) or []
            for prog in programs_raw:
                programs.append(DelayProgram(
                    type=prog.get("Type", "Unknown"),
                    cause=prog.get("Cause", "Unknown"),
                    avg_delay=prog.get("Avg", "Unknown"),
                    trend=prog.get("Trend", "Unknown"),
                ))
    except Exception as exc:
        logger.debug("NAS program extraction error for %s: %s", icao, exc)
    return programs


async def fetch_asws_status(icao: str) -> dict:
    """
    Fetch individual airport JSON from FAA ASWS.
    Returns {} on error.
    """
    icao = _normalize_icao(icao)
    url = f"{settings.faa_asws_url}/{icao}"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("FAA ASWS fetch failed for %s: %s", icao, exc)
            return {}


def _build_weather_summary(asws: dict) -> tuple[str, bool]:
    """Returns (weather_summary_string, has_weather_advisory)."""
    weather = asws.get("Weather", {}) or {}
    conditions = []
    vis = weather.get("Visibility", "") or ""
    wind = weather.get("Wind", "") or ""
    sky = weather.get("Sky", "") or ""
    temp = weather.get("Temp", "") or ""

    if vis:
        conditions.append(f"Visibility: {vis}")
    if wind:
        conditions.append(f"Wind: {wind}")
    if sky:
        conditions.append(f"Sky: {sky}")
    if temp:
        conditions.append(f"Temp: {temp}")

    summary = " | ".join(conditions) if conditions else "No weather data"

    # Heuristic: low visibility or severe wind = advisory
    advisory = any(
        kw in (sky + vis + wind).lower()
        for kw in ("overcast", "fog", "snow", "ice", "storm", "thunder", "rain", "gust", "TS")
    )

    return summary, advisory


async def get_airport_condition(raw_code: str) -> AirportCondition:
    """
    Primary entry point. Accepts ICAO or IATA. Fetches ASWS + NAS and returns AirportCondition.
    """
    icao = _normalize_icao(raw_code)
    iata = icao_to_iata(icao)
    name = _airport_name(icao)

    # Fetch all three sources concurrently
    import asyncio
    asws_data, nas_data, metar = await asyncio.gather(
        fetch_asws_status(icao),
        fetch_faa_nas_all(),
        fetch_metar(icao),
    )

    # FAA Aviation Weather Center only covers US airports; fall back to wttr.in
    # for international airports (OMDB, EGLL, etc.) or whenever AWC returns nothing.
    if metar is None and iata:
        metar = await fetch_wttr_fallback(iata)

    status = asws_data.get("Status", {}) or {}
    delay_flag = bool(status.get("ClosureBegin") or asws_data.get("Delay", False))

    programs = _extract_programs_for_airport(nas_data, icao)
    weather_summary, has_weather = _build_weather_summary(asws_data)

    # Upgrade advisory flag if METAR shows bad conditions
    if metar and not has_weather:
        bad_wx = any(kw in (metar.conditions_friendly + metar.sky_summary).lower()
                     for kw in ("rain", "snow", "fog", "mist", "thunder", "ice", "hail", "storm", "drizzle"))
        low_vis = metar.flight_category in ("IFR", "LIFR", "MVFR")
        has_weather = bad_wx or low_vis

    weather_block = asws_data.get("Weather", {}) or {}

    return AirportCondition(
        icao=icao,
        iata=iata,
        name=name or icao,
        delay=delay_flag or len(programs) > 0,
        closure=bool(status.get("ClosureBegin")),
        active_programs=programs,
        weather_summary=weather_summary,
        has_weather_advisory=has_weather,
        visibility=str(weather_block.get("Visibility", "")),
        wind=str(weather_block.get("Wind", "")),
        sky=str(weather_block.get("Sky", "")),
        temperature=str(weather_block.get("Temp", "")),
        metar=metar,
        raw_status=status,
    )
