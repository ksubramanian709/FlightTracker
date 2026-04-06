import { FlightStatus } from "@/lib/api";
import { Plane, Clock, ArrowRight } from "lucide-react";

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    active: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    landed: "bg-green-500/20 text-green-300 border-green-500/30",
    scheduled: "bg-slate-500/20 text-slate-300 border-slate-500/30",
    cancelled: "bg-red-500/20 text-red-300 border-red-500/30",
    diverted: "bg-orange-500/20 text-orange-300 border-orange-500/30",
  };
  return map[status] ?? "bg-slate-500/20 text-slate-300 border-slate-500/30";
}

export default function FlightCard({ flight }: { flight: FlightStatus }) {
  const hasDelay = flight.departure_delay_min > 0 || flight.arrival_delay_min > 0;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 space-y-4">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <Plane className="w-5 h-5 text-blue-400" />
            <span className="text-2xl font-bold">{flight.flight_number}</span>
          </div>
          <p className="text-slate-400 text-sm mt-0.5">{flight.airline}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <span className={`text-xs px-3 py-1 rounded-full border font-medium capitalize ${statusBadge(flight.status)}`}>
            {flight.status}
          </span>
          {hasDelay && (
            <span className="text-xs px-3 py-1 rounded-full border border-red-500/30 bg-red-500/20 text-red-300 font-medium">
              Delayed +{flight.departure_delay_min} min
            </span>
          )}
          {!hasDelay && flight.status !== "cancelled" && (
            <span className="text-xs px-3 py-1 rounded-full border border-green-500/30 bg-green-500/20 text-green-300 font-medium">
              On time
            </span>
          )}
        </div>
      </div>

      {/* Route */}
      <div className="flex items-center gap-4 py-4 border-y border-slate-800">
        <div className="text-center">
          <p className="text-3xl font-bold">{flight.origin_iata || flight.origin}</p>
          <p className="text-xs text-slate-500 mt-1">Departure</p>
        </div>
        <div className="flex-1 flex flex-col items-center gap-1">
          <ArrowRight className="w-5 h-5 text-slate-600" />
          {flight.tail_number && (
            <span className="text-xs text-slate-500">{flight.tail_number}</span>
          )}
        </div>
        <div className="text-center">
          <p className="text-3xl font-bold">{flight.destination_iata || flight.destination}</p>
          <p className="text-xs text-slate-500 mt-1">Arrival</p>
        </div>
      </div>

      {/* Times grid */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="space-y-2">
          <p className="text-xs text-slate-500 uppercase tracking-wider flex items-center gap-1">
            <Clock className="w-3 h-3" /> Departure
          </p>
          <div className="flex gap-3">
            <div>
              <p className="text-slate-400 text-xs">Scheduled</p>
              <p className="font-medium">{fmt(flight.scheduled_dep)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">Estimated</p>
              <p className={`font-medium ${flight.departure_delay_min > 0 ? "text-red-400" : "text-green-400"}`}>
                {fmt(flight.estimated_dep)}
              </p>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-xs text-slate-500 uppercase tracking-wider flex items-center gap-1">
            <Clock className="w-3 h-3" /> Arrival
          </p>
          <div className="flex gap-3">
            <div>
              <p className="text-slate-400 text-xs">Scheduled</p>
              <p className="font-medium">{fmt(flight.scheduled_arr)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">Estimated</p>
              <p className={`font-medium ${flight.arrival_delay_min > 0 ? "text-red-400" : "text-green-400"}`}>
                {fmt(flight.estimated_arr)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
