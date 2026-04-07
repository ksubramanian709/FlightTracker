# Flight Delay Analyzer ✈️

**Live: [flight-tracker-9z8lhp5fs-ksubramanian709-6914s-projects.vercel.app](https://flight-tracker-9z8lhp5fs-ksubramanian709-6914s-projects.vercel.app)**

Traces *why* a flight is delayed using live data from six sources: airline ACARS codes, aircraft rotation history, FAA ground programs, and live weather.

```
User enters: UA456
App returns:  Cause → Airline / Carrier (crew scheduling)   confidence 85%
              Inbound flight arrived 47 min late from DEN
              Delay originated at Denver
              Predicted: ~35 min (moderate)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js 16 frontend  (localhost:3000)                      │
│  FlightCard │ DelayAnalysis │ AircraftTimeline │ AirportStatus│
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────┐
│  FastAPI backend  (localhost:8000)                           │
│                                                              │
│  /api/delay-analysis  ←── orchestrates all sources          │
│  /api/flight-status   ←── FlightAware AeroAPI               │
│  /api/tail-history    ←── FlightAware AeroAPI               │
│  /api/airport-status  ←── FAA NAS + ASWS + METAR            │
└──────────┬───────────────────────┬──────────────────────────┘
           │                       │
    FlightAware AeroAPI     AviationStack / AeroDataBox
    FAA NAS / ASWS          AWC METAR / wttr.in (weather)
```

---

## Delay Signal Priority

| Priority | Signal | Source | Weight |
|---|---|---|---|
| 1 | Per-flight IATA delay reason code | AviationStack | 0.85 |
| 2 | Per-flight delay reason (fallback) | AeroDataBox | 0.75 |
| 3 | Direct inbound flight late (landed) | AeroAPI | 0.90 |
| 4 | Direct inbound flight late (airborne) | AeroAPI | 0.65 |
| 5 | Tail rotation history late | AeroAPI | 0.80 |
| 6 | FAA active NAS ground program | FAA NAS | 0.75 |
| 7 | METAR IFR/LIFR at departure | AWC / wttr.in | 0.60 |
| 8 | Weather advisory at either airport | AWC / wttr.in | 0.55 |
| 9 | Flight delayed, no external signal | — | 0.35 |

Confidence is boosted when multiple signals agree and penalised when they conflict.

### Delay cause buckets

| Cause | Meaning |
|---|---|
| `late_inbound` | Previous leg of the same aircraft ran late |
| `carrier` | Crew, maintenance, gate, fueling — airline-side (from ACARS) |
| `airport_nas` | FAA ground delay program or ATC restriction |
| `weather` | Low visibility / ceiling at departure or arrival |
| `operational_unknown` | Delay confirmed but no public signal found |

---

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your keys (see below)
uvicorn main:app --reload
# → http://localhost:8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `AEROAPI_KEY` | **Yes** | FlightAware AeroAPI. Free tier: 500 calls/month. [flightaware.com/aeroapi/portal](https://flightaware.com/aeroapi/portal/) |
| `AVIATIONSTACK_KEY` | Recommended | Per-flight IATA delay reason codes from airline ACARS. Free tier: 500 calls/month (HTTP only). [aviationstack.com](https://aviationstack.com) |
| `AERODATABOX_KEY` | Recommended | Delay reason fallback via RapidAPI. Free tier. [rapidapi.com/aedbx-aedbx/api/aerodatabox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox) |
| `OPENSKY_CLIENT_ID` | No | OpenSky Network — live ADS-B position. [opensky-network.org](https://opensky-network.org) |
| `OPENSKY_CLIENT_SECRET` | No | OpenSky Network client secret. |
| `NEXT_PUBLIC_API_URL` | No | Backend URL for the frontend. Defaults to `http://localhost:8000`. Set in `frontend/.env.local` for production. |

Copy `backend/.env.example` → `backend/.env` and fill in your keys.

---

## Data sources

| Source | Cost | What it provides |
|---|---|---|
| [FlightAware AeroAPI](https://flightaware.com/aeroapi/) | 500 free calls/month | Flight status, tail number, delays, inbound flight ID, rotation history |
| [AviationStack](https://aviationstack.com) | 500 free calls/month | Per-flight IATA delay reason codes from airline ACARS |
| [AeroDataBox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox) | Free tier (RapidAPI) | Delay reason fallback |
| [FAA NAS Status](https://nasstatus.faa.gov/api/airport-status-information) | Free, no key | Active ground delay programs and ground stops |
| [FAA ASWS](https://soa.smext.faa.gov/asws/api/airport/status/) | Free, no key | Per-airport weather text (US airports) |
| [FAA Aviation Weather Center](https://aviationweather.gov/api/data/metar) | Free, no key | Live METAR: temp, wind, visibility, flight category |
| [wttr.in](https://wttr.in) | Free, no key | Global weather fallback for international airports |

---

## API endpoints

| Method | Path | Params | Description |
|---|---|---|---|
| `GET` | `/api/delay-analysis` | `flight`, `date` | Full delay causality analysis |
| `GET` | `/api/flight-status` | `flight`, `date` | Raw flight status from FlightAware |
| `GET` | `/api/tail-history` | `tail`, `date` | Aircraft rotation legs |
| `GET` | `/api/airport-status` | `airport` (ICAO or IATA) | Live FAA + METAR conditions |
| `GET` | `/health` | — | Service health and data-source status |

---

## Delay prediction

```
predicted_delay = max(
    current_departure_delay,
    third_party_confirmed_delay,       ← AviationStack / AeroDataBox
    inbound_delay − turnaround_slack,  ← AeroAPI rotation
    current_delay + faa_avg_delay / 2, ← FAA NAS program avg
)
```

Labels: **on time** · **minor** (<15 min) · **moderate** (15–45 min) · **significant** (45–90 min) · **major** (>90 min)
