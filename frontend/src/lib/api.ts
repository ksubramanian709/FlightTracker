const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface DelayProgram {
  type: string;
  cause: string;
  avg_delay: string;
  trend: string;
}

export interface METARWeather {
  temp_c: number | null;
  temp_f: number | null;
  dewpoint_c: number | null;
  humidity_pct: number | null;
  wind_direction: number | null;
  wind_direction_label: string;
  wind_speed_kt: number | null;
  wind_gust_kt: number | null;
  visibility_sm: string;
  conditions: string;
  conditions_friendly: string;
  sky_summary: string;
  altimeter_inhg: number | null;
  raw_metar: string;
  flight_category: string;
  clouds: { cover: string; base: number | null }[];
}

export interface AirportCondition {
  icao: string;
  iata: string;
  name: string;
  delay: boolean;
  closure: boolean;
  active_programs: DelayProgram[];
  weather_summary: string;
  has_weather_advisory: boolean;
  visibility: string;
  wind: string;
  sky: string;
  temperature: string;
  metar: METARWeather | null;
}

export interface FlightStatus {
  flight_number: string;
  airline: string;
  tail_number: string | null;
  icao24: string | null;
  origin: string;
  destination: string;
  origin_iata: string;
  destination_iata: string;
  scheduled_dep: string | null;
  estimated_dep: string | null;
  scheduled_arr: string | null;
  estimated_arr: string | null;
  departure_delay_min: number;
  arrival_delay_min: number;
  status: string;
  data_source: string;
}

export interface TailLeg {
  icao24: string;
  callsign: string;
  origin: string;
  destination: string;
  scheduled_dep: string | null;
  actual_dep: string | null;
  scheduled_arr: string | null;
  actual_arr: string | null;
  departure_delay_min: number;
  arrival_delay_min: number;
  status: string;
  is_origin_of_delay: boolean;
}

export interface DelayChainLink {
  leg_callsign: string;
  origin: string;
  destination: string;
  arrival_delay_min: number;
  turnaround_available_min: number;
  is_root: boolean;
}

export interface DelayAnalysis {
  flight_number: string;
  cause: string;
  cause_label: string;
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  narrative: string;
  delay_origin_airport: string | null;
  chain: DelayChainLink[];
  predicted_delay_min: number;
  predicted_delay_label: string;
  signals_used: string[];
  data_sources: string[];
  sources_confirmed: number;
  data_mode: string;
}

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 90 } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  flightStatus: (flight: string, date?: string) =>
    apiFetch<FlightStatus>(`/api/flight-status?flight=${encodeURIComponent(flight)}${date ? `&date=${date}` : ""}`),

  tailHistory: (tail: string, date?: string) =>
    apiFetch<TailLeg[]>(`/api/tail-history?tail=${encodeURIComponent(tail)}${date ? `&date=${date}` : ""}`),

  airportStatus: (airport: string) =>
    apiFetch<AirportCondition>(`/api/airport-status?airport=${encodeURIComponent(airport)}`),

  delayAnalysis: (flight: string, date?: string) =>
    apiFetch<DelayAnalysis>(`/api/delay-analysis?flight=${encodeURIComponent(flight)}${date ? `&date=${date}` : ""}`),
};
