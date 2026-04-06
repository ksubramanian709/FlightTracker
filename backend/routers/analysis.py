"""
GET /api/delay-analysis?flight=UA456&date=2026-04-05

Orchestrates all data sources and runs the delay causality engine.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from config import settings
from delay_engine import run_delay_analysis
from models import DelayAnalysis
from services.aerodatabox import fetch_delay_signal as aerodatabox_fetch
from services.aviationstack import fetch_delay_signal as avstack_fetch
from services.faa_nas import get_airport_condition
from services.flight_adapter import get_client

router = APIRouter()


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


@router.get("/delay-analysis", response_model=DelayAnalysis)
async def delay_analysis(
    flight: Annotated[str, Query(description="Flight number, e.g. UA456")],
    date: Annotated[str | None, Query(description="Date YYYY-MM-DD (default: today)")] = None,
) -> JSONResponse:
    client = get_client()
    parsed_date = _parse_date(date)
    flight_ident = flight.strip()

    # Step 1: fetch flight status from FlightAware
    flight_status = await client.get_flight_status(flight_ident, parsed_date)
    if flight_status is None:
        raise HTTPException(status_code=404, detail=f"Flight '{flight}' not found in FlightAware AeroAPI")

    tail = flight_status.tail_number or ""
    origin = flight_status.origin or "KATL"
    destination = flight_status.destination or "KJFK"
    iata_ident = flight_status.flight_number or flight_ident

    # Step 2: fetch all data sources in parallel
    async def _empty_legs() -> list:
        return []

    async def _fetch_inbound():
        if flight_status.inbound_fa_flight_id:
            return await client.get_flight_by_fa_id(flight_status.inbound_fa_flight_id)
        return None

    async def _fetch_avstack():
        return await avstack_fetch(iata_ident, settings.aviationstack_key)

    async def _fetch_aerodatabox():
        return await aerodatabox_fetch(iata_ident, settings.aerodatabox_key)

    tail_task = client.get_tail_history(tail, parsed_date) if tail else _empty_legs()

    (
        tail_legs,
        faa_dep,
        faa_arr,
        inbound_flight,
        avstack_signal,
        aerodatabox_signal,
    ) = await asyncio.gather(
        tail_task,
        get_airport_condition(origin),
        get_airport_condition(destination),
        _fetch_inbound(),
        _fetch_avstack(),
        _fetch_aerodatabox(),
    )

    # Step 3: run delay causality engine
    result = await run_delay_analysis(
        flight_status,
        tail_legs,
        faa_dep,
        faa_arr,
        inbound_flight,
        avstack_signal,
        aerodatabox_signal,
    )

    response = JSONResponse(content=result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "public, max-age=90"
    return response
