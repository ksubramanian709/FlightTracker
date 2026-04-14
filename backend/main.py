"""
Flight Delay Analyzer — FastAPI backend.

Run:
  cd backend
  uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import flight, airport, analysis

app = FastAPI(
    title="Flight Delay Analyzer",
    description=(
        "Traces why a flight is delayed via FlightAware AeroAPI (real flight data + tail history), "
        "FAA NAS (live airport delay programs), and an aircraft rotation causality engine."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_checks() -> None:
    if not settings.aeroapi_key:
        raise RuntimeError(
            "\n\nAEROAPI_KEY is not set.\n"
            "Get a free key (500 calls/month) at https://flightaware.com/aeroapi/portal\n"
            "Then add AEROAPI_KEY=your_key to backend/.env\n"
        )


app.include_router(flight.router, prefix="/api", tags=["flight"])
app.include_router(airport.router, prefix="/api", tags=["airport"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": "03fd34c",
        "data_source": "FlightAware AeroAPI",
        "faa_nas": "enabled",
        "opensky": "enabled" if settings.opensky_enabled else "disabled (optional)",
    }
