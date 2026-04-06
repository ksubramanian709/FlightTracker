import { TailLeg, DelayChainLink } from "@/lib/api";
import { Plane, AlertCircle, CheckCircle, Clock } from "lucide-react";

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

function fmtDate(iso: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function LegRow({ leg, isLast, chainLink }: { leg: TailLeg; isLast: boolean; chainLink?: DelayChainLink }) {
  const isLate = leg.arrival_delay_min > 15;
  const isRoot = chainLink?.is_root;
  const turnaround = chainLink?.turnaround_available_min;

  return (
    <div className="relative flex gap-4">
      {/* Timeline line */}
      <div className="flex flex-col items-center">
        <div className={`w-3 h-3 rounded-full shrink-0 mt-1 z-10 border-2 ${
          isRoot
            ? "bg-red-500 border-red-400"
            : isLate
            ? "bg-orange-500 border-orange-400"
            : "bg-green-500 border-green-400"
        }`} />
        {!isLast && <div className="w-0.5 flex-1 bg-slate-700 mt-1" />}
      </div>

      {/* Content */}
      <div className={`pb-6 flex-1 rounded-xl p-3 mb-2 border ${
        isRoot
          ? "border-red-500/30 bg-red-500/5"
          : "border-slate-800 bg-slate-800/40"
      }`}>
        {isRoot && (
          <div className="flex items-center gap-1.5 text-xs text-red-400 font-medium mb-2">
            <AlertCircle className="w-3.5 h-3.5" />
            Delay likely started here
          </div>
        )}

        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Plane className="w-4 h-4 text-slate-500" />
            <span className="font-mono font-medium text-sm">{leg.callsign}</span>
            <span className="text-slate-500 text-sm">
              {leg.origin} → {leg.destination}
            </span>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            isLate
              ? "bg-orange-500/20 text-orange-300"
              : "bg-green-500/20 text-green-300"
          }`}>
            {isLate ? `+${leg.arrival_delay_min} min late` : "On time"}
          </span>
        </div>

        <div className="mt-2 grid grid-cols-2 gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            <span>Dep: {fmt(leg.actual_dep)} {leg.actual_dep ? `(${fmtDate(leg.actual_dep)})` : ""}</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            <span>Arr: {fmt(leg.actual_arr)}</span>
          </div>
        </div>

        {turnaround !== undefined && turnaround > 0 && (
          <div className={`mt-2 text-xs flex items-center gap-1 ${turnaround < 30 ? "text-red-400" : "text-slate-400"}`}>
            {turnaround < 30 ? (
              <AlertCircle className="w-3 h-3 shrink-0" />
            ) : (
              <CheckCircle className="w-3 h-3 shrink-0" />
            )}
            Turnaround window: {turnaround} min
            {turnaround < 30 && " (very tight)"}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AircraftTimeline({
  legs,
  chain,
}: {
  legs: TailLeg[];
  chain: DelayChainLink[];
}) {
  if (!legs.length) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Aircraft Rotation</h2>
        <p className="text-slate-500 text-sm">No rotation history available for this aircraft today.</p>
      </div>
    );
  }

  const chainMap = Object.fromEntries(chain.map((c) => [c.leg_callsign, c]));

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">
        Aircraft Rotation — {legs[0]?.icao24 || "Today"}
      </h2>
      <div className="space-y-0">
        {legs.map((leg, i) => (
          <LegRow
            key={`${leg.callsign}-${i}`}
            leg={leg}
            isLast={i === legs.length - 1}
            chainLink={chainMap[leg.callsign]}
          />
        ))}
      </div>
    </div>
  );
}
