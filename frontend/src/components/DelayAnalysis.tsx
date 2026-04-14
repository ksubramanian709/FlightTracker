import { DelayAnalysis } from "@/lib/api";
import {
  AlertTriangle,
  Cloud,
  Plane,
  HelpCircle,
  MapPin,
  TrendingUp,
  Wrench,
  CheckCircle2,
  Database,
  Info,
} from "lucide-react";

const CAUSE_CONFIG: Record<
  string,
  { label: string; icon: React.ReactNode; color: string; bg: string; border: string }
> = {
  late_inbound: {
    label: "Late Inbound Aircraft",
    icon: <Plane className="w-5 h-5" />,
    color: "text-orange-300",
    bg: "bg-orange-500/10",
    border: "border-orange-500/30",
  },
  airport_nas: {
    label: "Airport / NAS Restriction",
    icon: <AlertTriangle className="w-5 h-5" />,
    color: "text-yellow-300",
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/30",
  },
  weather: {
    label: "Weather",
    icon: <Cloud className="w-5 h-5" />,
    color: "text-blue-300",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
  },
  carrier: {
    label: "Airline / Carrier",
    icon: <Wrench className="w-5 h-5" />,
    color: "text-purple-300",
    bg: "bg-purple-500/10",
    border: "border-purple-500/30",
  },
  operational_unknown: {
    label: "Cause Unknown",
    icon: <HelpCircle className="w-5 h-5" />,
    color: "text-slate-400",
    bg: "bg-slate-700/30",
    border: "border-slate-600/30",
  },
};

const CONFIDENCE_BAR: Record<string, string> = {
  high:   "bg-emerald-500",
  medium: "bg-yellow-500",
  low:    "bg-red-500",
};

const CONFIDENCE_TEXT: Record<string, string> = {
  high:   "text-emerald-400",
  medium: "text-yellow-400",
  low:    "text-red-400",
};

function ConfidenceSection({ analysis }: { analysis: DelayAnalysis }) {
  const pct = Math.round(analysis.confidence * 100);
  const isUnknown =
    analysis.cause === "operational_unknown" && analysis.sources_confirmed === 0;

  if (isUnknown) {
    return (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
        <p className="text-sm text-slate-400 leading-relaxed">
          No public signal found. This is likely a crew, gate, or maintenance
          issue that airlines don&apos;t report through FAA or ADS-B channels.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center text-xs">
        <span className="text-slate-400 flex items-center gap-1.5">
          Confidence
          {analysis.sources_confirmed > 0 && (
            <span className="text-slate-600">
              · {analysis.sources_confirmed} source{analysis.sources_confirmed !== 1 ? "s" : ""} confirmed
            </span>
          )}
        </span>
        <span className={`font-semibold capitalize ${CONFIDENCE_TEXT[analysis.confidence_label]}`}>
          {analysis.confidence_label} — {pct}%
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${CONFIDENCE_BAR[analysis.confidence_label]}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[11px] text-slate-600 leading-snug">
        {analysis.confidence_label === "high" &&
          "Multiple independent sources agree on this cause."}
        {analysis.confidence_label === "medium" &&
          "At least one authoritative source supports this cause; some uncertainty remains."}
        {analysis.confidence_label === "low" &&
          "Limited data available — cause is inferred, not confirmed."}
      </p>
    </div>
  );
}

export default function DelayAnalysisCard({ analysis }: { analysis: DelayAnalysis }) {
  const cfg = CAUSE_CONFIG[analysis.cause] ?? CAUSE_CONFIG.operational_unknown;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 space-y-5">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
        Delay Analysis
      </h2>

      {/* Cause badge */}
      <div className={`flex items-center gap-3 rounded-xl border p-4 ${cfg.bg} ${cfg.border}`}>
        <span className={cfg.color}>{cfg.icon}</span>
        <div>
          <p className={`font-semibold ${cfg.color}`}>{analysis.cause_label}</p>
          <p className="text-xs text-slate-500 mt-0.5">Most likely root cause</p>
        </div>
      </div>

      {/* Confidence */}
      <ConfidenceSection analysis={analysis} />

      {/* Narrative */}
      <p className="text-sm text-slate-300 leading-relaxed bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
        {analysis.narrative}
      </p>

      {/* Origin airport */}
      {analysis.delay_origin_airport && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <MapPin className="w-4 h-4 text-red-400 shrink-0" />
          <span>
            Delay likely originated at{" "}
            <strong className="text-slate-200">{analysis.delay_origin_airport}</strong>
          </span>
        </div>
      )}

      {/* Predicted delay */}
      {analysis.predicted_delay_min > 0 && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <TrendingUp className="w-4 h-4 text-orange-400 shrink-0" />
          <span>
            Predicted delay:{" "}
            <strong className="text-slate-200">{analysis.predicted_delay_label}</strong>
          </span>
        </div>
      )}

      {/* Data sources */}
      {analysis.data_sources.length > 0 && (
        <div className="space-y-2 pt-1 border-t border-slate-800">
          <p className="text-[11px] text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
            <Database className="w-3 h-3" /> Sources analyzed
          </p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.data_sources.map((src) => (
              <span
                key={src}
                className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400"
              >
                <CheckCircle2 className="w-2.5 h-2.5 text-emerald-500 shrink-0" />
                {src}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Signals detail — collapsible */}
      {analysis.signals_used.length > 0 && (
        <details className="group">
          <summary className="text-[11px] text-slate-600 cursor-pointer hover:text-slate-400 select-none list-none flex items-center gap-1">
            <span className="group-open:rotate-90 inline-block transition-transform">▸</span>
            Raw signals ({analysis.signals_used.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {analysis.signals_used.map((s, i) => (
              <li key={i} className="text-[11px] text-slate-500 flex items-start gap-2">
                <span className="text-slate-700 mt-0.5 shrink-0">•</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
