import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api, type DelayAnalysis, type FlightStatus, type TailLeg, type AirportCondition } from "@/lib/api";
import FlightCard from "@/components/FlightCard";
import DelayAnalysisCard from "@/components/DelayAnalysis";
import AircraftTimeline from "@/components/AircraftTimeline";
import AirportStatus from "@/components/AirportStatus";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ date?: string }>;
}

export default async function FlightPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { date } = await searchParams;
  const flightNum = decodeURIComponent(id).toUpperCase();

  // Run analysis (orchestrates everything) and airport status in parallel
  let analysis: DelayAnalysis | undefined;
  let flight: FlightStatus | undefined;
  let tailLegs: TailLeg[] = [];
  let depAirport: AirportCondition | null = null;
  let arrAirport: AirportCondition | null = null;
  let error: string | null = null;

  try {
    analysis = await api.delayAnalysis(flightNum, date);
    flight = await api.flightStatus(flightNum, date);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load flight data";
  }

  if (error || !flight || !analysis) {
    return (
      <div className="max-w-xl mx-auto mt-16 text-center space-y-4">
        <div className="text-5xl">✈️</div>
        <h1 className="text-xl font-semibold">Flight not found</h1>
        <p className="text-slate-400 text-sm">{error ?? `No data found for ${flightNum}`}</p>
        <p className="text-slate-500 text-sm">
          Check the flight number and try again. Note: FlightAware free tier has 500 calls/month.
        </p>
        <Link href="/" className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 text-sm">
          <ArrowLeft className="w-4 h-4" /> Search again
        </Link>
      </div>
    );
  }

  // Fetch tail history and airport conditions (best-effort — don't fail the page)
  if (flight.tail_number) {
    try { tailLegs = await api.tailHistory(flight.tail_number, date); } catch { /* skip */ }
  }

  try {
    [depAirport, arrAirport] = await Promise.all([
      api.airportStatus(flight.origin),
      api.airportStatus(flight.destination),
    ]);
  } catch {
    depAirport = null;
    arrAirport = null;
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link href="/" className="inline-flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors">
        <ArrowLeft className="w-4 h-4" />
        New search
      </Link>

      {/* Top grid: flight card + delay analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <FlightCard flight={flight} />
        <DelayAnalysisCard analysis={analysis} />
      </div>

      {/* Bottom grid: timeline + airports */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AircraftTimeline legs={tailLegs} chain={analysis.chain} />
        {depAirport && arrAirport && (
          <AirportStatus departure={depAirport} arrival={arrAirport} />
        )}
      </div>

      {/* Data source note */}
      <p className="text-xs text-slate-600 text-right">
        Flight data: FlightAware AeroAPI · Airport conditions: FAA NAS &amp; ASWS
      </p>
    </div>
  );
}
