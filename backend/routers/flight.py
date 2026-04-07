"""
GET /api/flight-status?flight=UA456&date=2026-04-05
GET /api/tail-history?tail=N37293&date=2026-04-05
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from models import FlightStatus, TailLeg
from services.flight_adapter import AeroAPIClient, get_client
from utils import parse_date

router = APIRouter()


@router.get("/flight-status", response_model=FlightStatus)
async def flight_status(
    flight: Annotated[str, Query(description="Flight number, e.g. UA456")],
    date: Annotated[str | None, Query(description="Date YYYY-MM-DD (default: today)")] = None,
) -> JSONResponse:
    client: AeroAPIClient = get_client()
    result = await client.get_flight_status(flight.strip(), parse_date(date))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Flight '{flight}' not found")
    response = JSONResponse(content=result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "public, max-age=90"
    return response


@router.get("/tail-history", response_model=list[TailLeg])
async def tail_history(
    tail: Annotated[str, Query(description="Aircraft tail/registration number, e.g. N37293")],
    date: Annotated[str | None, Query(description="Date YYYY-MM-DD (default: today)")] = None,
) -> JSONResponse:
    client: AeroAPIClient = get_client()
    legs = await client.get_tail_history(tail.strip(), parse_date(date))
    response = JSONResponse(content=[l.model_dump(mode="json") for l in legs])
    response.headers["Cache-Control"] = "public, max-age=90"
    return response
