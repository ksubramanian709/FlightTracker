import { DelayAnalysis } from "@/lib/api";
import { AlertTriangle, Cloud, Plane, HelpCircle, MapPin, TrendingUp, Wrench } from "lucide-react";

const CAUSE_CONFIG: Record<string, { label: string; icon: React.ReactNode; color: string; bg: string }> = {
  late_inbound: {
    label: "Late Inbound Aircraft",
    icon: <Plane className="w-5 h-5" />,
    color: "text-orange-300",
    bg: "border-orange-500/30 bg-orange-500/10",
  },
  airport_nas: {
    label: "Airport / NAS Restriction",
    icon: <AlertTriangle className="w-5 h-5" />,
    color: "text-yellow-300",
    bg: "border-yellow-500/30 bg-yellow-500/10",
  },
  weather: {
    label: "Weather",
    icon: <Cloud className="w-5 h-5" />,
    color: "text-blue-300",
    bg: "border-blue-500/30 bg-blue-500/10",
  },
  carrier: {
    label: "Airline / Carrier",
    icon: <Wrench className="w-5 h-5" />,
    color: "text-purple-300",
    bg: "border-purple-500/30 bg-purple-500/10",
  },
  operational_unknown: {
    label: "Operational / Unknown",
    icon: <HelpCircle className="w-5 h-5" />,
    color: "text-slate-300",
    bg: "border-slate-500/30 bg-slate-500/10",
  },
};

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "bg-green-500",
  medium: "bg-yellow-500",
  low: "bg-red-500",
};

export default function DelayAnalysisCard({ analysis }: { analysis: DelayAnalysis }) {
  const cfg = CAUSE_CONFIG[analysis.cause] ?? CAUSE_CONFIG.operational_unknown;
  const confPct = Math.round(analysis.confidence * 100);

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 space-y-5">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Delay Analysis</h2>

      {/* Cause badge */}
      <div className={`flex items-center gap-3 rounded-xl border p-4 ${cfg.bg}`}>
        <span className={cfg.color}>{cfg.icon}</span>
        <div>
          <p className={`font-semibold ${cfg.color}`}>{analysis.cause_label}</p>
          <p className="text-xs text-slate-400 mt-0.5">Most likely cause</p>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-slate-400">
          <span>Confidence</span>
          <span className="font-medium capitalize">{analysis.confidence_label} — {confPct}%</span>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${CONFIDENCE_COLOR[analysis.confidence_label]}`}
            style={{ width: `${confPct}%` }}
          />
        </div>
      </div>

      {/* Narrative */}
      <p className="text-sm text-slate-300 leading-relaxed bg-slate-800/50 rounded-xl p-4 border border-slate-700">
        {analysis.narrative}
      </p>

      {/* Origin airport */}
      {analysis.delay_origin_airport && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <MapPin className="w-4 h-4 text-red-400 shrink-0" />
          <span>Delay likely originated at <strong className="text-slate-200">{analysis.delay_origin_airport}</strong></span>
        </div>
      )}

      {/* Predicted delay */}
      {analysis.predicted_delay_min > 0 && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <TrendingUp className="w-4 h-4 text-orange-400 shrink-0" />
          <span>Predicted delay: <strong className="text-slate-200">{analysis.predicted_delay_label}</strong></span>
        </div>
      )}

      {/* Signals used */}
      {analysis.signals_used.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs text-slate-500 uppercase tracking-wider">Signals used</p>
          <ul className="space-y-1">
            {analysis.signals_used.map((s, i) => (
              <li key={i} className="text-xs text-slate-400 flex items-start gap-2">
                <span className="text-slate-600 mt-0.5">•</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
