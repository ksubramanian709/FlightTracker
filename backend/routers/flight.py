"""
GET /api/flight-status?flight=UA456&date=2026-04-05
GET /api/tail-history?tail=N37293&date=2026-04-05
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from models import FlightStatus, TailLeg
from services.flight_adapter import AeroAPIClient, get_client

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


@router.get("/flight-status", response_model=FlightStatus)
async def flight_status(
    flight: Annotated[str, Query(description="Flight number, e.g. UA456")],
    date: Annotated[str | None, Query(description="Date YYYY-MM-DD (default: today)")] = None,
) -> JSONResponse:
    client: AeroAPIClient = get_client()
    result = await client.get_flight_status(flight.strip(), _parse_date(date))
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
    legs = await client.get_tail_history(tail.strip(), _parse_date(date))
    response = JSONResponse(content=[l.model_dump(mode="json") for l in legs])
    response.headers["Cache-Control"] = "public, max-age=90"
    return response
