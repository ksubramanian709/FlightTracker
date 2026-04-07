"use client";

import { useEffect, useState } from "react";
import { Plane } from "lucide-react";

interface Props {
  estimatedDep: string | null;
  estimatedArr: string | null;
}

function formatDuration(ms: number): string {
  if (ms <= 0) return "0m";
  const totalMin = Math.floor(ms / 60_000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function FlightProgress({ estimatedDep, estimatedArr }: Props) {
  const [progress, setProgress] = useState(0);
  const [elapsedLabel, setElapsedLabel] = useState("");
  const [remainingLabel, setRemainingLabel] = useState("");

  useEffect(() => {
    if (!estimatedDep || !estimatedArr) return;

    const dep = new Date(estimatedDep).getTime();
    const arr = new Date(estimatedArr).getTime();
    const total = arr - dep;
    if (total <= 0) return;

    const tick = () => {
      const now = Date.now();
      const elapsed = now - dep;
      const remaining = arr - now;
      const pct = Math.min(100, Math.max(0, (elapsed / total) * 100));
      setProgress(pct);
      setElapsedLabel(formatDuration(elapsed));
      setRemainingLabel(remaining > 0 ? formatDuration(remaining) : "Arriving");
    };

    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, [estimatedDep, estimatedArr]);

  // clamp icon position so it stays visually inside the track
  const iconPct = Math.min(96, Math.max(4, progress));

  return (
    <div className="space-y-2 w-full">
      {/* Track */}
      <div className="relative h-7 flex items-center">
        {/* Background rail */}
        <div className="absolute inset-x-0 h-[2px] bg-slate-700 rounded-full" />

        {/* Filled portion */}
        <div
          className="absolute left-0 h-[2px] bg-blue-500 rounded-full"
          style={{ width: `${progress}%`, transition: "width 1s linear" }}
        />

        {/* Departure dot */}
        <div className="absolute left-0 w-2 h-2 rounded-full bg-slate-500 -translate-x-1/2" />

        {/* Arrival dot */}
        <div className="absolute right-0 w-2 h-2 rounded-full bg-slate-500 translate-x-1/2" />

        {/* Plane icon */}
        <div
          className="absolute -translate-x-1/2"
          style={{ left: `${iconPct}%`, transition: "left 1s linear" }}
        >
          <div className="bg-blue-500 rounded-full p-[5px] shadow-lg shadow-blue-500/40 ring-2 ring-blue-400/30">
            <Plane className="w-3 h-3 text-white" fill="white" />
          </div>
        </div>
      </div>

      {/* Labels */}
      <div className="flex justify-between text-[11px]">
        <span className="text-slate-500">{elapsedLabel} elapsed</span>
        <span className="text-blue-400 font-semibold tabular-nums">
          {Math.round(progress)}% complete
        </span>
        <span className="text-slate-500">{remainingLabel} left</span>
      </div>
    </div>
  );
}
