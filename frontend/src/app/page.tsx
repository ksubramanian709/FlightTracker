"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Search, Plane, Shield, Zap, BarChart2 } from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const [flight, setFlight] = useState("");
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!flight.trim()) return;
    setLoading(true);
    const q = date ? `?date=${date}` : "";
    router.push(`/flight/${flight.trim().toUpperCase()}${q}`);
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[75vh] gap-10">
      {/* Hero */}
      <div className="text-center space-y-4 max-w-xl">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          Live data · FlightAware + FAA + METAR + TAF
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight leading-tight">
          Why is your flight<br />
          <span className="text-blue-400">delayed?</span>
        </h1>
        <p className="text-slate-400 text-base leading-relaxed">
          We trace the root cause — aircraft rotation, FAA ground programs,
          or weather — using six live data sources with confidence scoring.
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="w-full max-w-md space-y-3">
        <div className="relative">
          <Plane className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
          <input
            type="text"
            value={flight}
            onChange={(e) => setFlight(e.target.value.toUpperCase())}
            placeholder="Flight number — UA456, DL204, AA101"
            className="w-full pl-10 pr-4 py-3.5 rounded-xl bg-slate-800/80 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all"
            required
            autoFocus
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full px-3 py-3.5 rounded-xl bg-slate-800/80 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all [color-scheme:dark]"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !flight.trim()}
            className="flex items-center gap-2 px-6 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed font-semibold text-sm transition-all shadow-lg shadow-blue-500/20"
          >
            <Search className="w-4 h-4" />
            {loading ? "Loading…" : "Analyze"}
          </button>
        </div>
      </form>

      {/* Feature pills */}
      <div className="flex flex-wrap gap-3 justify-center text-xs text-slate-400 max-w-lg">
        {[
          { icon: <Plane className="w-3.5 h-3.5" />, label: "Aircraft rotation tracing" },
          { icon: <Shield className="w-3.5 h-3.5" />, label: "FAA ground programs" },
          { icon: <Zap className="w-3.5 h-3.5" />, label: "Live METAR + TAF weather" },
          { icon: <BarChart2 className="w-3.5 h-3.5" />, label: "Multi-source confidence" },
        ].map(({ icon, label }) => (
          <div key={label} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-800/60 border border-slate-700/50">
            <span className="text-slate-500">{icon}</span>
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
