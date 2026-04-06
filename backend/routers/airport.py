"""
GET /api/airport-status?airport={ICAO_or_IATA}

Returns live FAA NAS + ASWS conditions for one airport.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from models import AirportCondition
from services.faa_nas import get_airport_condition

router = APIRouter()


@router.get("/airport-status", response_model=AirportCondition)
async def airport_status(
    airport: str = Query(..., description="Airport ICAO (KSFO) or IATA (SFO) code"),
) -> JSONResponse:
    if len(airport.strip()) < 3:
        raise HTTPException(status_code=400, detail="Airport code must be at least 3 characters")
    condition = await get_airport_condition(airport.strip().upper())
    response = JSONResponse(content=condition.model_dump(mode="json"))
    response.headers["Cache-Control"] = "public, max-age=90"
    return response
