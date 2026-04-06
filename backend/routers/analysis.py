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

from delay_engine import run_delay_analysis
from models import DelayAnalysis
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

    # Step 1: fetch flight status from FlightAware
    flight_status = await client.get_flight_status(flight.strip(), parsed_date)
    if flight_status is None:
        raise HTTPException(status_code=404, detail=f"Flight '{flight}' not found in FlightAware AeroAPI")

    # Step 2: fetch tail rotation history + FAA conditions in parallel
    tail = flight_status.tail_number or ""
    origin = flight_status.origin or "KATL"
    destination = flight_status.destination or "KJFK"

    async def _empty_legs() -> list:
        return []

    tail_task = client.get_tail_history(tail, parsed_date) if tail else _empty_legs()
    faa_dep_task = get_airport_condition(origin)
    faa_arr_task = get_airport_condition(destination)

    tail_legs, faa_dep, faa_arr = await asyncio.gather(
        tail_task, faa_dep_task, faa_arr_task
    )

    # Step 3: run delay causality engine
    result = await run_delay_analysis(flight_status, tail_legs, faa_dep, faa_arr)

    response = JSONResponse(content=result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "public, max-age=90"
    return response
