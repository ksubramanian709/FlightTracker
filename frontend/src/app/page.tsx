"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Search, Plane } from "lucide-react";

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
    <div className="flex flex-col items-center justify-center min-h-[70vh] gap-8">
      {/* Hero */}
      <div className="text-center space-y-3">
        <div className="text-6xl">✈️</div>
        <h1 className="text-4xl font-bold tracking-tight">Why is my flight delayed?</h1>
        <p className="text-slate-400 max-w-lg text-base leading-relaxed">
          Enter a flight number and we&apos;ll trace the delay back to its root cause —
          aircraft rotation, FAA ground programs, or weather — using live FlightAware and FAA data.
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="w-full max-w-md space-y-3">
        <div className="relative">
          <Plane className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-5 h-5" />
          <input
            type="text"
            value={flight}
            onChange={(e) => setFlight(e.target.value)}
            placeholder="Flight number — e.g. UA456, DL204, AA101"
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            required
            autoFocus
          />
        </div>

        <div className="flex gap-2">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="flex-1 px-3 py-3 rounded-xl bg-slate-800 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
          <button
            type="submit"
            disabled={loading || !flight.trim()}
            className="flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm transition-colors"
          >
            <Search className="w-4 h-4" />
            {loading ? "Searching…" : "Analyze"}
          </button>
        </div>
      </form>

      {/* Example searches */}
      <div className="text-sm text-slate-500 flex flex-wrap gap-2 justify-center">
        <span>Try:</span>
        {["UA456", "DL204", "AA101", "WN1234"].map((f) => (
          <button
            key={f}
            onClick={() => { setFlight(f); }}
            className="px-3 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
          >
            {f}
          </button>
        ))}
      </div>
    </div>
  );
}
