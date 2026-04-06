"""
Shared Pydantic models returned by all API endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Airport / FAA
# ---------------------------------------------------------------------------

class DelayProgram(BaseModel):
    type: str          # "Ground Delay", "Ground Stop", "Arrival", "Departure", "Airspace Flow"
    cause: str         # "Weather", "Volume", "Runway", "Equipment", "Other"
    avg_delay: str     # human string, e.g. "47 minutes"
    trend: str         # "Increasing" | "Decreasing" | "Stable"


class METARWeather(BaseModel):
    """Decoded METAR observation from FAA Aviation Weather Center."""
    temp_c: float | None = None
    temp_f: float | None = None
    dewpoint_c: float | None = None
    humidity_pct: int | None = None
    wind_direction: int | None = None         # degrees true
    wind_direction_label: str = ""            # e.g. "SW (220°)"
    wind_speed_kt: int | None = None
    wind_gust_kt: int | None = None
    visibility_sm: str = ""                   # e.g. "10+ SM"
    conditions: str = ""                      # raw wx string, e.g. "-RA"
    conditions_friendly: str = ""             # e.g. "Light Rain"
    sky_summary: str = ""                     # e.g. "Broken clouds at 2,500 ft"
    altimeter_inhg: float | None = None
    raw_metar: str = ""
    flight_category: str = ""                 # VFR | MVFR | IFR | LIFR
    clouds: list[dict] = []


class AirportCondition(BaseModel):
    icao: str
    iata: str
    name: str
    delay: bool
    closure: bool
    active_programs: list[DelayProgram]
    weather_summary: str
    has_weather_advisory: bool
    visibility: str = ""
    wind: str = ""
    sky: str = ""
    temperature: str = ""
    metar: METARWeather | None = None
    raw_status: dict = {}


# ---------------------------------------------------------------------------
# Flight / Aircraft
# ---------------------------------------------------------------------------

class TailLeg(BaseModel):
    icao24: str
    callsign: str
    origin: str          # ICAO
    destination: str     # ICAO
    scheduled_dep: datetime | None = None
    actual_dep: datetime | None = None
    scheduled_arr: datetime | None = None
    actual_arr: datetime | None = None
    departure_delay_min: int = 0
    arrival_delay_min: int = 0
    status: Literal["completed", "in_flight", "scheduled", "cancelled", "unknown"] = "unknown"
    is_origin_of_delay: bool = False


class FlightStatus(BaseModel):
    flight_number: str
    airline: str
    tail_number: str | None = None
    icao24: str | None = None        # OpenSky hex transponder
    origin: str                      # ICAO
    destination: str                 # ICAO
    origin_iata: str = ""
    destination_iata: str = ""
    scheduled_dep: datetime | None = None
    estimated_dep: datetime | None = None
    scheduled_arr: datetime | None = None
    estimated_arr: datetime | None = None
    departure_delay_min: int = 0
    arrival_delay_min: int = 0
    status: Literal["scheduled", "active", "landed", "cancelled", "diverted", "unknown"] = "unknown"
    inbound_fa_flight_id: str | None = None   # previous leg's AeroAPI flight ID
    fa_flight_id: str | None = None           # this flight's AeroAPI flight ID
    data_source: Literal["aeroapi"] = "aeroapi"


# ---------------------------------------------------------------------------
# Delay Analysis
# ---------------------------------------------------------------------------

CauseBucket = Literal[
    "late_inbound",
    "airport_nas",
    "weather",
    "operational_unknown",
]


class DelayChainLink(BaseModel):
    leg_callsign: str
    origin: str
    destination: str
    arrival_delay_min: int
    turnaround_available_min: int
    is_root: bool = False


class DelayAnalysis(BaseModel):
    flight_number: str
    cause: CauseBucket
    cause_label: str          # human-readable
    confidence: float         # 0.0 – 1.0
    confidence_label: Literal["high", "medium", "low"]
    narrative: str
    delay_origin_airport: str | None = None
    chain: list[DelayChainLink] = []
    predicted_delay_min: int = 0
    predicted_delay_label: str = ""
    signals_used: list[str] = []
    data_mode: Literal["live"] = "live"
