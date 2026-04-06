"""
Runtime configuration loaded from backend/.env

Required:
  AEROAPI_KEY              — FlightAware AeroAPI free key
                             Get one at https://flightaware.com/aeroapi/portal

Optional (delay reason codes — strongly recommended):
  AVIATIONSTACK_KEY        — free tier: 500 calls/month (HTTP only on free plan)
                             Sign up at https://aviationstack.com
  AERODATABOX_KEY          — RapidAPI key for AeroDataBox (free tier available)
                             Sign up at https://rapidapi.com/aedbx-aedbx/api/aerodatabox

Optional (enriches live aircraft position):
  OPENSKY_CLIENT_ID        — free account at opensky-network.org
  OPENSKY_CLIENT_SECRET
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # FlightAware AeroAPI (required)
    aeroapi_key: str = ""
    aeroapi_base_url: str = "https://aeroapi.flightaware.com/aeroapi"

    # AviationStack — per-flight IATA delay reason codes (optional but recommended)
    # Free tier uses HTTP only; upgrade for HTTPS.
    aviationstack_key: str = ""

    # AeroDataBox via RapidAPI — delay reason fallback (optional)
    aerodatabox_key: str = ""

    # OpenSky Network (optional — enriches live position)
    opensky_client_id: str = ""
    opensky_client_secret: str = ""
    opensky_base_url: str = "https://opensky-network.org/api"
    opensky_token_url: str = "https://opensky-network.org/api/auth/token"

    # FAA endpoints (no key needed — always on)
    faa_nas_url: str = "https://nasstatus.faa.gov/api/airport-status-information"
    faa_asws_url: str = "https://soa.smext.faa.gov/asws/api/airport/status"

    @property
    def opensky_enabled(self) -> bool:
        return bool(self.opensky_client_id.strip() and self.opensky_client_secret.strip())


settings = Settings()
