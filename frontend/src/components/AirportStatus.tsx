import { AirportCondition, METARWeather } from "@/lib/api";
import {
  AlertTriangle,
  Wind,
  Eye,
  Thermometer,
  Droplets,
  Gauge,
  CloudRain,
  Cloud,
  Sun,
  CheckCircle,
  CloudSnow,
  Zap,
} from "lucide-react";

// ── Flight category badge ──────────────────────────────────────────────────

function FlightCategoryBadge({ category }: { category: string }) {
  const map: Record<string, { label: string; classes: string }> = {
    VFR:  { label: "VFR",  classes: "bg-emerald-500/20 border-emerald-500/40 text-emerald-300" },
    MVFR: { label: "MVFR", classes: "bg-blue-500/20   border-blue-500/40   text-blue-300"    },
    IFR:  { label: "IFR",  classes: "bg-red-500/20    border-red-500/40    text-red-300"      },
    LIFR: { label: "LIFR", classes: "bg-fuchsia-500/20 border-fuchsia-500/40 text-fuchsia-300" },
  };
  const entry = map[category.toUpperCase()];
  if (!entry) return null;
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${entry.classes}`}>
      {entry.label}
    </span>
  );
}

// ── Weather condition icon ─────────────────────────────────────────────────

function ConditionIcon({ conditions, category }: { conditions: string; category: string }) {
  const c = conditions.toLowerCase();
  const cls = "w-10 h-10";
  if (c.includes("thunder"))   return <Zap      className={`${cls} text-yellow-400`} />;
  if (c.includes("snow"))      return <CloudSnow className={`${cls} text-sky-300`}   />;
  if (c.includes("rain") || c.includes("drizzle"))
                               return <CloudRain className={`${cls} text-blue-400`}  />;
  if (c.includes("fog") || c.includes("mist"))
                               return <Cloud     className={`${cls} text-slate-400`} />;
  if (category === "VFR")      return <Sun       className={`${cls} text-yellow-300`}/>;
  return                              <Cloud     className={`${cls} text-slate-500`} />;
}

// ── Wind direction arrow (rotates to point in wind direction) ──────────────

function WindArrow({ deg }: { deg: number | null }) {
  if (deg === null) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      className="w-4 h-4 shrink-0 text-slate-300"
      style={{ transform: `rotate(${deg}deg)` }}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="7 10 12 5 17 10" />
    </svg>
  );
}

// ── METAR weather panel ────────────────────────────────────────────────────

function METARPanel({ metar }: { metar: METARWeather }) {
  const hasConds = !!metar.conditions_friendly;

  return (
    <div className="space-y-3">
      {/* Top row: big temperature + condition icon */}
      <div className="flex items-center justify-between">
        <div className="flex items-end gap-1">
          {metar.temp_f !== null ? (
            <>
              <span className="text-3xl font-bold leading-none">{Math.round(metar.temp_f)}°</span>
              <span className="text-sm text-slate-400 mb-0.5">F</span>
              {metar.temp_c !== null && (
                <span className="text-sm text-slate-500 mb-0.5 ml-1">({Math.round(metar.temp_c)}°C)</span>
              )}
            </>
          ) : metar.temp_c !== null ? (
            <>
              <span className="text-3xl font-bold leading-none">{Math.round(metar.temp_c)}°</span>
              <span className="text-sm text-slate-400 mb-0.5">C</span>
            </>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1">
          <ConditionIcon
            conditions={metar.conditions_friendly}
            category={metar.flight_category}
          />
          {metar.flight_category && (
            <FlightCategoryBadge category={metar.flight_category} />
          )}
        </div>
      </div>

      {/* Conditions label */}
      {hasConds && (
        <p className="text-sm font-medium text-slate-200">{metar.conditions_friendly}</p>
      )}

      {/* Sky / clouds */}
      {metar.sky_summary && (
        <p className="text-xs text-slate-400">{metar.sky_summary}</p>
      )}

      {/* Stat grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-slate-400">
        {/* Wind */}
        {metar.wind_speed_kt !== null && (
          <div className="flex items-center gap-1.5">
            <WindArrow deg={metar.wind_direction} />
            <Wind className="w-3.5 h-3.5 shrink-0" />
            <span>
              {metar.wind_direction_label
                ? `${metar.wind_direction_label} `
                : ""}
              {metar.wind_speed_kt} kt
              {metar.wind_gust_kt ? ` gusts ${metar.wind_gust_kt} kt` : ""}
            </span>
          </div>
        )}

        {/* Visibility */}
        {metar.visibility_sm && (
          <div className="flex items-center gap-1.5">
            <Eye className="w-3.5 h-3.5 shrink-0" />
            <span>Vis: {metar.visibility_sm}</span>
          </div>
        )}

        {/* Humidity */}
        {metar.humidity_pct !== null && (
          <div className="flex items-center gap-1.5">
            <Droplets className="w-3.5 h-3.5 shrink-0" />
            <span>Humidity: {metar.humidity_pct}%</span>
          </div>
        )}

        {/* Dewpoint */}
        {metar.dewpoint_c !== null && (
          <div className="flex items-center gap-1.5">
            <Thermometer className="w-3.5 h-3.5 shrink-0" />
            <span>Dew: {metar.dewpoint_c}°C</span>
          </div>
        )}

        {/* Altimeter */}
        {metar.altimeter_inhg !== null && (
          <div className="flex items-center gap-1.5">
            <Gauge className="w-3.5 h-3.5 shrink-0" />
            <span>{metar.altimeter_inhg} inHg</span>
          </div>
        )}
      </div>

      {/* Raw METAR, collapsed */}
      {metar.raw_metar && (
        <details className="group">
          <summary className="text-[10px] text-slate-600 cursor-pointer hover:text-slate-500 select-none list-none">
            Raw METAR ▸
          </summary>
          <p className="mt-1 font-mono text-[10px] text-slate-500 break-all leading-relaxed">
            {metar.raw_metar}
          </p>
        </details>
      )}
    </div>
  );
}

// ── FAA program row ────────────────────────────────────────────────────────

function ProgramRow({
  type,
  cause,
  avg_delay,
  trend,
}: {
  type: string;
  cause: string;
  avg_delay: string;
  trend: string;
}) {
  return (
    <div className="rounded-lg bg-slate-800/60 border border-slate-700/50 p-3 text-sm">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-medium text-yellow-300">{type}</span>
        <span className="text-xs text-slate-400 capitalize">{trend}</span>
      </div>
      <div className="mt-1 flex gap-4 text-xs text-slate-400">
        <span>
          Cause: <span className="text-slate-300">{cause}</span>
        </span>
        <span>
          Avg delay:{" "}
          <span className="text-orange-300 font-medium">{avg_delay}</span>
        </span>
      </div>
    </div>
  );
}

// ── Airport card ───────────────────────────────────────────────────────────

function AirportCard({
  airport,
  role,
}: {
  airport: AirportCondition;
  role: string;
}) {
  const hasPrograms = airport.active_programs.length > 0;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-800/30 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <span className="text-[10px] text-slate-500 uppercase tracking-widest">
            {role}
          </span>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-2xl font-bold">
              {airport.iata || airport.icao}
            </span>
            {airport.name && (
              <span className="text-xs text-slate-400 truncate max-w-[180px]">
                {airport.name}
              </span>
            )}
          </div>
          <span className="text-[10px] text-slate-600">{airport.icao}</span>
        </div>

        {/* Status pill */}
        {hasPrograms ? (
          <span className="text-xs px-2 py-1 rounded-full bg-red-500/20 border border-red-500/30 text-red-300 font-medium whitespace-nowrap">
            FAA Delays Active
          </span>
        ) : airport.delay ? (
          <span className="text-xs px-2 py-1 rounded-full bg-yellow-500/20 border border-yellow-500/30 text-yellow-300 font-medium whitespace-nowrap">
            Delays Reported
          </span>
        ) : (
          <div className="flex items-center gap-1 text-xs text-emerald-400">
            <CheckCircle className="w-3.5 h-3.5" />
            Normal ops
          </div>
        )}
      </div>

      {/* METAR weather block */}
      {airport.metar ? (
        <METARPanel metar={airport.metar} />
      ) : airport.visibility || airport.wind || airport.temperature || airport.sky ? (
        /* Fallback: ASWS text fields */
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
      ) : (
        <p className="text-xs text-slate-600 italic">Weather data unavailable</p>
      )}

      {/* FAA delay programs */}
      {hasPrograms && (
        <div className="space-y-2 pt-1 border-t border-slate-700/40">
          <p className="text-xs text-slate-500 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Active FAA Programs
          </p>
          {airport.active_programs.map((p, i) => (
            <ProgramRow key={i} {...p} />
          ))}
        </div>
      )}

      {/* Weather advisory banner */}
      {airport.has_weather_advisory && !hasPrograms && (
        <div className="text-xs text-amber-300 flex items-center gap-1.5 pt-1 border-t border-slate-700/40">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          Weather advisory — may impact operations
        </div>
      )}
    </div>
  );
}

// ── Export ─────────────────────────────────────────────────────────────────

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
        Airport Conditions — Live FAA + METAR
      </h2>
      <div className="space-y-3">
        <AirportCard airport={departure} role="Departure" />
        <AirportCard airport={arrival} role="Arrival" />
      </div>
    </div>
  );
}
