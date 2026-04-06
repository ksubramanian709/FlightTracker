"""
Delay causality rule engine.

Infers the most likely cause of a flight delay from three independent signal sources:
  1. FAA NAS active delay programs at the departure airport
  2. Late inbound aircraft (tail-number rotation tracing)
  3. Weather advisories at departure or arrival airport

Confidence is boosted when multiple signals agree on the same root cause.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from models import (
    AirportCondition,
    CauseBucket,
    DelayAnalysis,
    DelayChainLink,
    FlightStatus,
    TailLeg,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal signal type
# ---------------------------------------------------------------------------

@dataclass
class _Signal:
    cause: CauseBucket
    detail: str
    weight: float          # 0.0 – 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minutes_between(earlier: datetime | None, later: datetime | None) -> int | None:
    """Return minutes from earlier to later, or None if either is missing."""
    if not earlier or not later:
        return None
    diff = (later - earlier).total_seconds() / 60
    return int(diff)


def _primary_faa_cause(airport: AirportCondition) -> str:
    """Extract human-readable cause from FAA programs, e.g. 'Weather', 'Volume'."""
    if not airport.active_programs:
        return "Unknown"
    causes = [p.cause for p in airport.active_programs if p.cause]
    weather_causes = [c for c in causes if "weather" in c.lower() or "wx" in c.lower()]
    if weather_causes:
        return "Weather"
    volume_causes = [c for c in causes if "volume" in c.lower() or "traffic" in c.lower()]
    if volume_causes:
        return "Volume / Congestion"
    return causes[0] if causes else "Congestion"


def _faa_delay_minutes(airport: AirportCondition) -> int:
    """Best-guess numeric delay from FAA program avg_delay strings like '47 minutes'."""
    for prog in airport.active_programs:
        raw = (prog.avg_delay or "").lower().replace("minutes", "").replace("mins", "").strip()
        parts = raw.split()
        for part in parts:
            try:
                return int(part)
            except ValueError:
                continue
    return 0


# ---------------------------------------------------------------------------
# Core rule engine
# ---------------------------------------------------------------------------

def _collect_signals(
    flight: FlightStatus,
    tail_legs: list[TailLeg],
    faa_dep: AirportCondition,
    faa_arr: AirportCondition,
) -> list[_Signal]:
    signals: list[_Signal] = []

    # --- Signal 1: FAA active delay program at departure airport ---------------
    if faa_dep.active_programs:
        primary_cause = _primary_faa_cause(faa_dep)
        if "weather" in primary_cause.lower():
            cause_bucket: CauseBucket = "weather"
        else:
            cause_bucket = "airport_nas"
        signals.append(_Signal(
            cause=cause_bucket,
            detail=f"FAA active program at {faa_dep.iata or faa_dep.icao}: {primary_cause}",
            weight=0.70,
        ))

    # --- Signal 2: Late inbound aircraft / rotation ----------------------------
    # Find the most recent completed leg before the current flight
    now = datetime.now(timezone.utc)
    prev_legs = [
        leg for leg in tail_legs
        if leg.callsign.upper() != flight.flight_number.upper()
        and (leg.actual_dep or now) < now
    ]
    if prev_legs:
        prev_legs.sort(key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc))
        prev = prev_legs[-1]

        if prev.arrival_delay_min > 15:
            turnaround = _minutes_between(prev.actual_arr, flight.scheduled_dep)
            turnaround_tight = turnaround is not None and turnaround < 50
            weight = 0.85 if turnaround_tight else 0.60
            detail = (
                f"Aircraft arrived {prev.arrival_delay_min}min late from "
                f"{prev.origin} → {prev.destination}"
            )
            if turnaround is not None:
                detail += f"; turnaround window only {turnaround}min"
            signals.append(_Signal(cause="late_inbound", detail=detail, weight=weight))

    # --- Signal 3: Weather advisory at either airport -------------------------
    weather_airports = []
    if faa_dep.has_weather_advisory:
        weather_airports.append(faa_dep.iata or faa_dep.icao)
    if faa_arr.has_weather_advisory:
        weather_airports.append(faa_arr.iata or faa_arr.icao)
    if weather_airports:
        # Only add weather signal if not already covered by a stronger NAS signal
        existing_causes = {s.cause for s in signals}
        if "weather" not in existing_causes:
            signals.append(_Signal(
                cause="weather",
                detail=f"Weather advisory active at {', '.join(weather_airports)}",
                weight=0.55,
            ))

    # --- Default: operational / unknown ---------------------------------------
    if not signals or (len(signals) == 1 and signals[0].weight < 0.40):
        signals.append(_Signal(
            cause="operational_unknown",
            detail="No public signal; likely crew, maintenance, or gate issue",
            weight=0.25,
        ))

    return signals


def _aggregate(signals: list[_Signal]) -> tuple[CauseBucket, float, list[_Signal]]:
    """
    Pick the dominant cause by highest weight. Boost confidence when signals agree.
    Penalise slightly when signals conflict.
    """
    if not signals:
        return "operational_unknown", 0.20, signals

    # Sort by weight descending
    sorted_sigs = sorted(signals, key=lambda s: -s.weight)
    dominant = sorted_sigs[0]

    base_confidence = dominant.weight

    agreeing = [s for s in signals if s.cause == dominant.cause]
    conflicting = [s for s in signals if s.cause != dominant.cause and s.cause != "operational_unknown"]

    # +5 % per extra agreeing signal, capped at +15 %
    boost = min(0.15, 0.05 * (len(agreeing) - 1))
    # -10 % per conflicting signal
    penalty = min(0.20, 0.10 * len(conflicting))

    confidence = min(0.97, max(0.10, base_confidence + boost - penalty))
    return dominant.cause, confidence, sorted_sigs


def _confidence_label(c: float) -> Literal["high", "medium", "low"]:
    if c >= 0.70:
        return "high"
    if c >= 0.45:
        return "medium"
    return "low"


_CAUSE_LABELS: dict[CauseBucket, str] = {
    "late_inbound": "Late inbound aircraft",
    "airport_nas": "Airport / NAS restriction",
    "weather": "Weather",
    "operational_unknown": "Operational / Unknown",
}


def _build_narrative(
    flight: FlightStatus,
    cause: CauseBucket,
    signals: list[_Signal],
    tail_legs: list[TailLeg],
    faa_dep: AirportCondition,
    chain: list[DelayChainLink],
) -> str:
    label = _CAUSE_LABELS[cause]
    dep_label = flight.origin_iata or flight.origin
    arr_label = flight.destination_iata or flight.destination

    if cause == "late_inbound" and tail_legs:
        prev_legs = [l for l in tail_legs if l.callsign.upper() != flight.flight_number.upper()]
        if prev_legs:
            prev_legs.sort(key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc))
            prev = prev_legs[-1]
            t = _minutes_between(prev.actual_arr, flight.scheduled_dep)
            t_str = f"only {t}min turnaround" if t is not None else "a short turnaround"
            root = chain[0].origin if chain else prev.origin
            return (
                f"Likely delayed by a late inbound aircraft. This aircraft previously operated "
                f"{prev.origin} → {prev.destination} and arrived {prev.arrival_delay_min} min late, "
                f"leaving {t_str} before this {dep_label} → {arr_label} departure. "
                f"The delay likely originated at {root}."
            )

    if cause == "airport_nas":
        prog_text = "; ".join(
            f"{p.type} ({p.cause}, avg {p.avg_delay})" for p in faa_dep.active_programs
        )
        return (
            f"Likely delayed by an FAA/NAS restriction at {dep_label}. "
            f"Active programs: {prog_text or 'ground delay or ground stop in effect'}."
        )

    if cause == "weather":
        weather_detail = next((s.detail for s in signals if s.cause == "weather"), "")
        return (
            f"Likely delayed by weather conditions. {weather_detail}. "
            f"Weather is impacting {dep_label} or {arr_label} operations."
        )

    return (
        f"The cause could not be determined from public data. This is likely an operational issue "
        f"(crew scheduling, maintenance, gate conflict) that is not visible in FAA or ADS-B records."
    )


def _find_chain_origin(
    flight: FlightStatus,
    tail_legs: list[TailLeg],
) -> tuple[list[DelayChainLink], str | None]:
    """
    Walk backwards through the rotation to find where the delay first appeared.
    """
    chain: list[DelayChainLink] = []
    if not tail_legs:
        return chain, None

    now = datetime.now(timezone.utc)
    prev_legs = sorted(
        [l for l in tail_legs if (l.actual_dep or now) <= now],
        key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc),
    )

    root_airport: str | None = None
    for leg in prev_legs:
        turnaround = _minutes_between(
            leg.actual_arr,
            (prev_legs[prev_legs.index(leg) + 1].actual_dep
             if prev_legs.index(leg) + 1 < len(prev_legs) else flight.scheduled_dep),
        )
        is_root = leg.arrival_delay_min > 15 and (turnaround is None or turnaround < 50)
        if is_root and root_airport is None:
            root_airport = leg.origin
        link = DelayChainLink(
            leg_callsign=leg.callsign,
            origin=leg.origin,
            destination=leg.destination,
            arrival_delay_min=leg.arrival_delay_min,
            turnaround_available_min=turnaround or 0,
            is_root=is_root,
        )
        chain.append(link)

    # Add the current flight as the final link
    chain.append(DelayChainLink(
        leg_callsign=flight.flight_number,
        origin=flight.origin,
        destination=flight.destination,
        arrival_delay_min=flight.arrival_delay_min,
        turnaround_available_min=0,
        is_root=False,
    ))

    return chain, root_airport


def _predict_delay(
    flight: FlightStatus,
    tail_legs: list[TailLeg],
    faa_dep: AirportCondition,
) -> tuple[int, str]:
    """
    Rules-based delay length prediction.
    """
    current = flight.departure_delay_min
    if current > 0:
        base = current
    else:
        base = 0

    # Propagated inbound delay minus turnaround slack
    inbound_contribution = 0
    prev_legs = sorted(
        [l for l in tail_legs if l.callsign.upper() != flight.flight_number.upper()],
        key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc),
    )
    if prev_legs:
        prev = prev_legs[-1]
        if prev.arrival_delay_min > 0:
            turnaround = _minutes_between(prev.actual_arr, flight.scheduled_dep) or 0
            min_turn = 25  # minimum turnaround needed
            slack = max(0, turnaround - min_turn)
            inbound_contribution = max(0, prev.arrival_delay_min - slack)

    # FAA program adds expected delay
    faa_contribution = _faa_delay_minutes(faa_dep)

    predicted = max(base, inbound_contribution, base + faa_contribution // 2)

    if predicted == 0:
        return 0, "On time or minimal delay expected"
    elif predicted < 15:
        return predicted, f"~{predicted} min (minor)"
    elif predicted < 45:
        return predicted, f"~{predicted} min (moderate)"
    elif predicted < 90:
        return predicted, f"~{predicted} min (significant)"
    else:
        return predicted, f"~{predicted} min (major)"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_delay_analysis(
    flight: FlightStatus,
    tail_legs: list[TailLeg],
    faa_dep: AirportCondition,
    faa_arr: AirportCondition,
) -> DelayAnalysis:
    signals = _collect_signals(flight, tail_legs, faa_dep, faa_arr)
    cause, confidence, sorted_signals = _aggregate(signals)
    chain, origin_airport = _find_chain_origin(flight, tail_legs)
    narrative = _build_narrative(flight, cause, sorted_signals, tail_legs, faa_dep, chain)
    predicted_min, predicted_label = _predict_delay(flight, tail_legs, faa_dep)

    return DelayAnalysis(
        flight_number=flight.flight_number,
        cause=cause,
        cause_label=_CAUSE_LABELS[cause],
        confidence=round(confidence, 3),
        confidence_label=_confidence_label(confidence),
        narrative=narrative,
        delay_origin_airport=origin_airport,
        chain=chain,
        predicted_delay_min=predicted_min,
        predicted_delay_label=predicted_label,
        signals_used=[s.detail for s in sorted_signals],
        data_mode="live",
    )
