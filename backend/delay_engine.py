"""
Delay causality rule engine.

Infers the most likely cause of a flight delay from multiple signal sources
in priority order:

  0a. AviationStack per-flight IATA delay reason code (highest signal quality)
  0b. AeroDataBox per-flight delay reason (fallback when AviationStack has none)
  1.  Direct inbound flight late and already landed (inbound_fa_flight_id)
  2.  Direct inbound flight still airborne — projected late arrival
  3.  Late inbound via tail-number rotation history
  4.  FAA NAS active delay program at departure airport
  5.  Weather advisory (METAR/wttr flight category or advisory flag)
  6.  Fallback: flight is significantly delayed with no external cause found

Confidence is boosted when multiple signals agree on the same root cause,
and penalised when signals conflict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from models import (
    AirportCondition,
    CauseBucket,
    DelayAnalysis,
    DelayChainLink,
    FlightStatus,
    TailLeg,
)

if TYPE_CHECKING:
    from services.aviationstack import AviationStackSignal
    from services.aerodatabox import AeroDataBoxSignal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal signal type
# ---------------------------------------------------------------------------

@dataclass
class _Signal:
    cause: CauseBucket
    detail: str
    weight: float          # 0.0 – 1.0
    source: str = ""       # e.g. "aviationstack", "aerodatabox", "aeroapi", "faa"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minutes_between(earlier: datetime | None, later: datetime | None) -> int | None:
    if not earlier or not later:
        return None
    diff = (later - earlier).total_seconds() / 60
    return int(diff)


def _primary_faa_cause(airport: AirportCondition) -> str:
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
    inbound_flight: FlightStatus | None = None,
    avstack_signal: "AviationStackSignal | None" = None,
    aerodatabox_signal: "AeroDataBoxSignal | None" = None,
) -> list[_Signal]:
    signals: list[_Signal] = []

    # --- Signal 0a: AviationStack per-flight delay reason (best source) -------
    if avstack_signal is not None:
        signals.append(_Signal(
            cause=avstack_signal.cause,
            detail=avstack_signal.detail,
            weight=avstack_signal.weight,
            source="aviationstack",
        ))

    # --- Signal 0b: AeroDataBox delay reason (fallback) -----------------------
    # Only use if AviationStack gave no useful reason-coded signal
    avstack_has_reason = (
        avstack_signal is not None
        and avstack_signal.cause != "operational_unknown"
    )
    if aerodatabox_signal is not None and not avstack_has_reason:
        signals.append(_Signal(
            cause=aerodatabox_signal.cause,
            detail=aerodatabox_signal.detail,
            weight=aerodatabox_signal.weight,
            source="aerodatabox",
        ))

    # --- Signal 1: Direct inbound flight — already landed ---------------------
    if inbound_flight and inbound_flight.status == "landed" and inbound_flight.arrival_delay_min > 15:
        turnaround = _minutes_between(inbound_flight.estimated_arr, flight.scheduled_dep)
        turnaround_tight = turnaround is not None and turnaround < 50
        weight = 0.90 if turnaround_tight else 0.70
        detail = (
            f"Inbound flight {inbound_flight.flight_number} "
            f"({inbound_flight.origin_iata or inbound_flight.origin} → "
            f"{inbound_flight.destination_iata or inbound_flight.destination}) "
            f"arrived {inbound_flight.arrival_delay_min}min late"
        )
        if turnaround is not None:
            detail += f"; only {turnaround}min turnaround"
        signals.append(_Signal(cause="late_inbound", detail=detail, weight=weight, source="aeroapi"))

    # --- Signal 2: Direct inbound flight — still airborne (blind spot fix) ----
    elif inbound_flight and inbound_flight.status == "active" and inbound_flight.departure_delay_min > 15:
        turnaround = _minutes_between(inbound_flight.estimated_arr, flight.scheduled_dep)
        detail = (
            f"Inbound flight {inbound_flight.flight_number} is currently airborne "
            f"and running {inbound_flight.departure_delay_min}min late; "
            f"projected to arrive late before this departure"
        )
        if turnaround is not None:
            detail += f" ({turnaround}min turnaround window)"
        signals.append(_Signal(
            cause="late_inbound",
            detail=detail,
            weight=0.65,
            source="aeroapi",
        ))

    # --- Signal 3: Late inbound via tail rotation history --------------------
    elif tail_legs:
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
                weight = 0.80 if turnaround_tight else 0.60
                detail = (
                    f"Aircraft arrived {prev.arrival_delay_min}min late from "
                    f"{prev.origin} → {prev.destination}"
                )
                if turnaround is not None:
                    detail += f"; turnaround window only {turnaround}min"
                signals.append(_Signal(cause="late_inbound", detail=detail, weight=weight, source="aeroapi"))

    # --- Signal 4: FAA active delay program at departure airport -------------
    if faa_dep.active_programs:
        primary_cause = _primary_faa_cause(faa_dep)
        cause_bucket: CauseBucket = "weather" if "weather" in primary_cause.lower() else "airport_nas"
        signals.append(_Signal(
            cause=cause_bucket,
            detail=f"FAA active program at {faa_dep.iata or faa_dep.icao}: {primary_cause}",
            weight=0.75,
            source="faa",
        ))

    # --- Signal 5: Weather advisory at either airport ------------------------
    weather_airports = []
    if faa_dep.has_weather_advisory:
        weather_airports.append(faa_dep.iata or faa_dep.icao)
    if faa_arr.has_weather_advisory:
        weather_airports.append(faa_arr.iata or faa_arr.icao)
    if weather_airports:
        existing_causes = {s.cause for s in signals}
        if "weather" not in existing_causes:
            signals.append(_Signal(
                cause="weather",
                detail=f"Weather advisory active at {', '.join(weather_airports)}",
                weight=0.55,
                source="metar",
            ))

    # Also check METAR flight category for bad conditions at departure
    if faa_dep.metar and faa_dep.metar.flight_category in ("IFR", "LIFR"):
        existing_causes = {s.cause for s in signals}
        if "weather" not in existing_causes:
            signals.append(_Signal(
                cause="weather",
                detail=(
                    f"Departure airport {faa_dep.iata or faa_dep.icao} is "
                    f"{faa_dep.metar.flight_category} — "
                    f"{faa_dep.metar.conditions_friendly or 'low visibility/ceiling'}"
                ),
                weight=0.60,
                source="metar",
            ))

    # --- Signal 6: Fallback —- flight delayed with no external cause ----------
    if flight.departure_delay_min > 30 and not signals:
        signals.append(_Signal(
            cause="operational_unknown",
            detail=(
                f"Flight is {flight.departure_delay_min}min delayed; "
                f"no external NAS/weather signal found — likely crew, gate, or maintenance"
            ),
            weight=0.35,
            source="fallback",
        ))
    elif not signals:
        signals.append(_Signal(
            cause="operational_unknown",
            detail="No public signal found; likely crew, maintenance, or gate issue",
            weight=0.25,
            source="fallback",
        ))

    return signals


def _aggregate(signals: list[_Signal]) -> tuple[CauseBucket, float, list[_Signal]]:
    if not signals:
        return "operational_unknown", 0.20, signals

    sorted_sigs = sorted(signals, key=lambda s: -s.weight)
    dominant = sorted_sigs[0]
    base_confidence = dominant.weight

    agreeing = [s for s in signals if s.cause == dominant.cause]
    conflicting = [s for s in signals if s.cause != dominant.cause and s.cause != "operational_unknown"]

    boost = min(0.15, 0.05 * (len(agreeing) - 1))
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
    "carrier": "Airline / Carrier",
    "operational_unknown": "Operational / Unknown",
}


def _build_narrative(
    flight: FlightStatus,
    cause: CauseBucket,
    signals: list[_Signal],
    tail_legs: list[TailLeg],
    faa_dep: AirportCondition,
    chain: list[DelayChainLink],
    inbound_flight: FlightStatus | None = None,
) -> str:
    dep_label = flight.origin_iata or flight.origin
    arr_label = flight.destination_iata or flight.destination

    # Pull the top signal's detail for direct-source narratives
    top_signal = signals[0] if signals else None

    if cause == "carrier":
        detail = top_signal.detail if top_signal else ""
        # Extract the human-readable reason from the detail string
        reason_part = detail.split("delay reason:")[-1].strip() if "delay reason:" in detail else detail
        return (
            f"{flight.flight_number} is delayed due to an airline/carrier issue: "
            f"{reason_part}. "
            f"This type of delay (crew availability, maintenance, gate conflict, or ground operations) "
            f"is not visible in public FAA or ADS-B records."
        )

    if cause == "late_inbound":
        # Prefer direct inbound flight info
        if inbound_flight and inbound_flight.arrival_delay_min > 0:
            t = _minutes_between(inbound_flight.estimated_arr, flight.scheduled_dep)
            t_str = f"only {t}min turnaround" if t is not None else "a tight turnaround"
            root = chain[0].origin if chain else (inbound_flight.origin_iata or inbound_flight.origin)
            status_note = " (currently airborne)" if inbound_flight.status == "active" else ""
            return (
                f"Likely delayed by a late inbound aircraft. The inbound flight "
                f"{inbound_flight.flight_number}{status_note} "
                f"({inbound_flight.origin_iata or inbound_flight.origin} → "
                f"{inbound_flight.destination_iata or inbound_flight.destination}) "
                f"is running {inbound_flight.departure_delay_min or inbound_flight.arrival_delay_min} min late, "
                f"leaving {t_str} before this {dep_label} → {arr_label} departure. "
                f"The delay likely originated at {root}."
            )
        # Fall back to rotation history
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

    # operational_unknown — show delay amount if we have it
    if flight.departure_delay_min > 0:
        return (
            f"{flight.flight_number} is currently delayed by {flight.departure_delay_min} min. "
            f"No public NAS program or weather advisory was found at {dep_label}. "
            f"This is likely an operational issue (crew scheduling, maintenance, or gate conflict) "
            f"that is not visible in public FAA or ADS-B records."
        )
    return (
        f"No delay or cause signals found for {flight.flight_number}. "
        f"The flight may be on time, or any delay is not yet reflected in public data."
    )


def _find_chain_origin(
    flight: FlightStatus,
    tail_legs: list[TailLeg],
    inbound_flight: FlightStatus | None = None,
) -> tuple[list[DelayChainLink], str | None]:
    chain: list[DelayChainLink] = []

    if inbound_flight:
        turnaround = _minutes_between(inbound_flight.estimated_arr, flight.scheduled_dep)
        delay_used = inbound_flight.arrival_delay_min or inbound_flight.departure_delay_min
        is_root = delay_used > 15
        chain.append(DelayChainLink(
            leg_callsign=inbound_flight.flight_number,
            origin=inbound_flight.origin,
            destination=inbound_flight.destination,
            arrival_delay_min=delay_used,
            turnaround_available_min=turnaround or 0,
            is_root=is_root,
        ))
        chain.append(DelayChainLink(
            leg_callsign=flight.flight_number,
            origin=flight.origin,
            destination=flight.destination,
            arrival_delay_min=flight.arrival_delay_min,
            turnaround_available_min=0,
            is_root=False,
        ))
        root_airport = inbound_flight.origin if is_root else None
        return chain, root_airport

    if not tail_legs:
        return chain, None

    now = datetime.now(timezone.utc)
    prev_legs = sorted(
        [l for l in tail_legs if (l.actual_dep or now) <= now],
        key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc),
    )

    root_airport: str | None = None
    for leg in prev_legs:
        idx = prev_legs.index(leg)
        next_dep = (
            prev_legs[idx + 1].actual_dep if idx + 1 < len(prev_legs)
            else flight.scheduled_dep
        )
        turnaround = _minutes_between(leg.actual_arr, next_dep)
        is_root = leg.arrival_delay_min > 15 and (turnaround is None or turnaround < 50)
        if is_root and root_airport is None:
            root_airport = leg.origin
        chain.append(DelayChainLink(
            leg_callsign=leg.callsign,
            origin=leg.origin,
            destination=leg.destination,
            arrival_delay_min=leg.arrival_delay_min,
            turnaround_available_min=turnaround or 0,
            is_root=is_root,
        ))

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
    inbound_flight: FlightStatus | None = None,
    avstack_signal: "AviationStackSignal | None" = None,
    aerodatabox_signal: "AeroDataBoxSignal | None" = None,
) -> tuple[int, str]:
    current = flight.departure_delay_min

    # Use delay amounts from the new signals as a floor
    third_party_delay = 0
    if avstack_signal:
        third_party_delay = max(third_party_delay, avstack_signal.dep_delay_min, avstack_signal.arr_delay_min)
    if aerodatabox_signal:
        third_party_delay = max(third_party_delay, aerodatabox_signal.dep_delay_min, aerodatabox_signal.arr_delay_min)

    inbound_contribution = 0
    if inbound_flight:
        inbound_delay = inbound_flight.arrival_delay_min or inbound_flight.departure_delay_min
        if inbound_delay > 0:
            turnaround = _minutes_between(inbound_flight.estimated_arr, flight.scheduled_dep) or 0
            slack = max(0, turnaround - 25)
            inbound_contribution = max(0, inbound_delay - slack)
    elif tail_legs:
        prev_legs = sorted(
            [l for l in tail_legs if l.callsign.upper() != flight.flight_number.upper()],
            key=lambda l: l.actual_dep or datetime.min.replace(tzinfo=timezone.utc),
        )
        if prev_legs:
            prev = prev_legs[-1]
            if prev.arrival_delay_min > 0:
                turnaround = _minutes_between(prev.actual_arr, flight.scheduled_dep) or 0
                slack = max(0, turnaround - 25)
                inbound_contribution = max(0, prev.arrival_delay_min - slack)

    faa_contribution = _faa_delay_minutes(faa_dep)
    predicted = max(current, third_party_delay, inbound_contribution, current + faa_contribution // 2)

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
    inbound_flight: FlightStatus | None = None,
    avstack_signal: "AviationStackSignal | None" = None,
    aerodatabox_signal: "AeroDataBoxSignal | None" = None,
) -> DelayAnalysis:
    signals = _collect_signals(
        flight, tail_legs, faa_dep, faa_arr, inbound_flight,
        avstack_signal, aerodatabox_signal,
    )
    cause, confidence, sorted_signals = _aggregate(signals)
    chain, origin_airport = _find_chain_origin(flight, tail_legs, inbound_flight)
    narrative = _build_narrative(flight, cause, sorted_signals, tail_legs, faa_dep, chain, inbound_flight)
    predicted_min, predicted_label = _predict_delay(
        flight, tail_legs, faa_dep, inbound_flight, avstack_signal, aerodatabox_signal,
    )

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
