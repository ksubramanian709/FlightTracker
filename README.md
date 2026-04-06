# Flight Delay Analyzer ✈️

**🌐 Live: [flight-tracker-9z8lhp5fs-ksubramanian709-6914s-projects.vercel.app](https://flight-tracker-9z8lhp5fs-ksubramanian709-6914s-projects.vercel.app)**

Traces *why* a flight is delayed across aircraft rotations, FAA ground programs, and weather advisories using live data.

```
User enters: UA456
App returns:  Likely cause → Late inbound aircraft (confidence 82%)
              Aircraft previously operated DEN → SFO and arrived 47 min late.
              Delay likely originated in Denver.
              Predicted delay: ~35 min (moderate)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js 16 frontend  (localhost:3000)                      │
│  ┌──────────┐ ┌───────────────┐ ┌────────────┐ ┌────────┐  │
│  │FlightCard│ │DelayAnalysis  │ │Aircraft    │ │Airport │  │
│  │          │ │(cause+score)  │ │Timeline    │ │Status  │  │
│  └──────────┘ └───────────────┘ └────────────┘ └────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────┐
│  FastAPI backend  (localhost:8000)                           │
│                                                              │
│  /api/delay-analysis  ←── orchestrates everything           │
│  /api/flight-status   ←── FlightAware AeroAPI               │
│  /api/tail-history    ←── FlightAware AeroAPI               │
│  /api/airport-status  ←── FAA NAS + ASWS (free, no key)     │
└──────────┬────────────────────────┬─────────────────────────┘
           │                        │
    FlightAware AeroAPI        FAA NAS / ASWS
    (500 calls/month free)     (public, no key)
```

### Delay causality rule engine

```
if dep_airport has active FAA delay program (weather cause)   → weather
if dep_airport has active FAA delay program (volume cause)    → airport_nas
if inbound same-tail arrived late AND turnaround < 50 min     → late_inbound  (high weight)
if inbound same-tail arrived late AND turnaround ≥ 50 min     → late_inbound  (medium weight)
if weather advisory at either airport                         → weather
else                                                          → operational_unknown

Confidence boosted when signals agree; penalised when conflicting.
```

---

## Quick start

### 1. Clone and enter the project

```bash
git clone <your-repo>
cd flight-delay-analyzer
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy the env template
cp .env.example .env
# Edit .env and paste your AEROAPI_KEY (see below)

uvicorn main:app --reload
# → http://localhost:8000
```

### 3. Frontend

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
| `AEROAPI_KEY` | **Yes** | FlightAware AeroAPI key. Free tier: 500 calls/month. Get it at [flightaware.com/aeroapi/portal](https://flightaware.com/aeroapi/portal/). |
| `AVIATIONSTACK_KEY` | Recommended | Per-flight IATA delay reason codes. Free tier: 500 calls/month (HTTP only). Get it at [aviationstack.com](https://aviationstack.com). |
| `AERODATABOX_KEY` | Recommended | Delay reason fallback via RapidAPI. Free tier at [rapidapi.com/aedbx-aedbx/api/aerodatabox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox). |
| `OPENSKY_CLIENT_ID` | No | OpenSky Network OAuth2 client ID — enriches live aircraft position. Leave blank to disable. |
| `OPENSKY_CLIENT_SECRET` | No | OpenSky Network OAuth2 client secret. |
| `NEXT_PUBLIC_API_URL` | No (frontend) | Backend URL; defaults to `http://localhost:8000`. Set in `frontend/.env.local` for production. |

Copy `backend/.env.example` → `backend/.env` and fill in `AEROAPI_KEY`. Add `AVIATIONSTACK_KEY` and `AERODATABOX_KEY` to unlock specific delay reason codes.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/delay-analysis` | Full delay causality analysis. Params: `flight`, `date` (YYYY-MM-DD). |
| `GET` | `/api/flight-status` | Raw FlightAware flight status. Params: `flight`, `date`. |
| `GET` | `/api/tail-history` | Aircraft rotation legs. Params: `tail`, `date`. |
| `GET` | `/api/airport-status` | FAA NAS + ASWS conditions. Params: `airport` (ICAO or IATA). |
| `GET` | `/health` | Service health + data-source status. |

---

## Data sources

| Source | Cost | What it provides |
|---|---|---|
| [FlightAware AeroAPI](https://flightaware.com/aeroapi/) | 500 free calls/month | Flight status, tail numbers, aircraft rotation history, inbound flight ID |
| [AviationStack](https://aviationstack.com) | 500 free calls/month | Per-flight IATA delay reason codes from airline ACARS (crew, weather, NAS, gate) |
| [AeroDataBox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox) | Free tier via RapidAPI | Delay reason fallback when AviationStack has no code |
| [FAA NAS Status](https://nasstatus.faa.gov/api/airport-status-information) | Free, no key | Active ground delay programs, ground stops, cause & trend |
| [FAA ASWS](https://soa.smext.faa.gov/asws/api/airport/status/) | Free, no key | Per-airport weather: visibility, wind, sky, temperature |
| [FAA Aviation Weather Center](https://aviationweather.gov/api/data/metar) | Free, no key | Live METAR observations: temp, wind, visibility, flight category |
| [wttr.in](https://wttr.in) | Free, no key | Fallback weather for international airports not covered by AWC |
| [OpenSky Network](https://opensky-network.org/) | Free (optional) | ADS-B arrival/departure times, live aircraft state vectors |

---

## Delay prediction logic

No ML required — rules-based estimate:

```
predicted_delay = max(
    current_departure_delay,
    inbound_delay − turnaround_slack,
    current_delay + faa_avg_delay / 2,
)
```

Labels: on-time · minor (<15 min) · moderate (15–45 min) · significant (45–90 min) · major (>90 min)

---

## Upgrade path

| Version | What to add |
|---|---|
| V1 (current) | Live analysis, FAA conditions, rotation tracing |
| V2 | Persist analyses to SQLite/Postgres for historic trending |
| V3 | ML delay-length regression trained on AeroAPI historic data |
| V4 | Push notifications ("your flight just went to major delay") |
| V5 | Airline fleet-wide view — which tails are cascading across the network |
