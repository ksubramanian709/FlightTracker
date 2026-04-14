import Link from "next/link";
import { ArrowLeft, RefreshCw } from "lucide-react";
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

  let analysis: DelayAnalysis | undefined;
  let flight: FlightStatus | undefined;
  let tailLegs: TailLeg[] = [];
  let depAirport: AirportCondition | null = null;
  let arrAirport: AirportCondition | null = null;
  let error: string | null = null;

  try {
    [analysis, flight] = await Promise.all([
      api.delayAnalysis(flightNum, date),
      api.flightStatus(flightNum, date),
    ]);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load flight data";
  }

  if (error || !flight || !analysis) {
    return (
      <div className="max-w-md mx-auto mt-20 text-center space-y-5">
        <div className="w-16 h-16 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center mx-auto text-3xl">
          ✈️
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold">Flight not found</h1>
          <p className="text-slate-400 text-sm leading-relaxed">
            {error ?? `No data found for ${flightNum}`}
          </p>
          <p className="text-slate-600 text-xs">
            Check the flight number and try again. FlightAware free tier allows 500 calls/month.
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-sm transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Search again
        </Link>
      </div>
    );
  }

  // Fetch tail history and airport conditions in parallel (best-effort)
  await Promise.allSettled([
    flight.tail_number
      ? api.tailHistory(flight.tail_number, date).then((legs) => { tailLegs = legs; }).catch(() => {})
      : Promise.resolve(),
    Promise.all([
      api.airportStatus(flight.origin),
      api.airportStatus(flight.destination),
    ])
      .then(([dep, arr]) => { depAirport = dep; arrAirport = arr; })
      .catch(() => {}),
  ]);

  const dateStr = date
    ? new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "Today";

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          New search
        </Link>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <RefreshCw className="w-3 h-3" />
          Live · {dateStr}
        </div>
      </div>

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

      <p className="text-xs text-slate-700 text-right">
        FlightAware AeroAPI · AviationStack · AeroDataBox · FAA NAS &amp; METAR · FAA TAF
      </p>
    </div>
  );
}
