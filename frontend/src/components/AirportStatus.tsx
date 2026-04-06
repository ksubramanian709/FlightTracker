import { AirportCondition } from "@/lib/api";
import { AlertTriangle, Cloud, Wind, Eye, Thermometer, CheckCircle } from "lucide-react";

function ProgramRow({ type, cause, avg_delay, trend }: { type: string; cause: string; avg_delay: string; trend: string }) {
  return (
    <div className="rounded-lg bg-slate-800/60 border border-slate-700/50 p-3 text-sm">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-medium text-yellow-300">{type}</span>
        <span className="text-xs text-slate-400 capitalize">{trend}</span>
      </div>
      <div className="mt-1 flex gap-4 text-xs text-slate-400">
        <span>Cause: <span className="text-slate-300">{cause}</span></span>
        <span>Avg delay: <span className="text-orange-300 font-medium">{avg_delay}</span></span>
      </div>
    </div>
  );
}

function AirportCard({ airport, role }: { airport: AirportCondition; role: string }) {
  const hasPrograms = airport.active_programs.length > 0;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-800/30 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs text-slate-500 uppercase tracking-wider">{role}</span>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xl font-bold">{airport.iata || airport.icao}</span>
            {airport.name && (
              <span className="text-xs text-slate-400 truncate max-w-[160px]">{airport.name}</span>
            )}
          </div>
        </div>
        {hasPrograms ? (
          <span className="text-xs px-2 py-1 rounded-full bg-red-500/20 border border-red-500/30 text-red-300 font-medium">
            FAA Delays
          </span>
        ) : airport.delay ? (
          <span className="text-xs px-2 py-1 rounded-full bg-yellow-500/20 border border-yellow-500/30 text-yellow-300 font-medium">
            Delays
          </span>
        ) : (
          <div className="flex items-center gap-1 text-xs text-green-400">
            <CheckCircle className="w-3.5 h-3.5" />
            Normal
          </div>
        )}
      </div>

      {/* FAA programs */}
      {hasPrograms && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Active FAA Programs
          </p>
          {airport.active_programs.map((p, i) => (
            <ProgramRow key={i} {...p} />
          ))}
        </div>
      )}

      {/* Weather */}
      <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
        {airport.visibility && (
          <div className="flex items-center gap-1">
            <Eye className="w-3 h-3 shrink-0" />
            <span>Vis: {airport.visibility}</span>
          </div>
        )}
        {airport.wind && (
          <div className="flex items-center gap-1">
            <Wind className="w-3 h-3 shrink-0" />
            <span>{airport.wind}</span>
          </div>
        )}
        {airport.temperature && (
          <div className="flex items-center gap-1">
            <Thermometer className="w-3 h-3 shrink-0" />
            <span>{airport.temperature}</span>
          </div>
        )}
        {airport.sky && (
          <div className="flex items-center gap-1">
            <Cloud className="w-3 h-3 shrink-0" />
            <span>{airport.sky}</span>
          </div>
        )}
      </div>

      {airport.has_weather_advisory && (
        <div className="text-xs text-blue-300 flex items-center gap-1">
          <Cloud className="w-3 h-3" />
          Weather advisory active
        </div>
      )}
    </div>
  );
}

export default function AirportStatus({
  departure,
  arrival,
}: {
  departure: AirportCondition;
  arrival: AirportCondition;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 space-y-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
        Airport Conditions — Live FAA Data
      </h2>
      <div className="space-y-3">
        <AirportCard airport={departure} role="Departure" />
        <AirportCard airport={arrival} role="Arrival" />
      </div>
    </div>
  );
}
