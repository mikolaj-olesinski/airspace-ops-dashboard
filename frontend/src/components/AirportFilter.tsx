import type { AirportPrediction } from "../lib/types";
import { AIRPORT_COORDS } from "../lib/airports";

const RISK_COLOR: Record<string, string> = {
  low: "var(--risk-low)",
  medium: "var(--risk-medium)",
  high: "var(--risk-high)",
};

/** A sticky airport filter shared by every chart on the dashboard (RiskBars, RiskRadar,
 * the Airspace Load area chart, both gauges, and the map) -- picking one here, or
 * clicking an airport directly on the map, narrows all of them to that airport at once
 * instead of each panel only being clickable in isolation. */
export default function AirportFilter({
  selected,
  onSelect,
  predictions,
}: {
  selected: string | null;
  onSelect: (code: string | null) => void;
  predictions: AirportPrediction[];
}) {
  const byCode = new Map(predictions.map((p) => [p.airport, p]));
  const codes = Object.keys(AIRPORT_COORDS);

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-[var(--panel-border)] px-5 py-2">
      <span className="mr-1 text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">Filter</span>
      <button
        onClick={() => onSelect(null)}
        className={`rounded-full border px-3 py-1 text-[11px] transition-colors ${
          selected === null
            ? "border-white/40 bg-white/10 text-white"
            : "border-[var(--panel-border-strong)] text-[var(--text-mid)] hover:border-white/30 hover:text-white"
        }`}
      >
        All airports
      </button>
      {codes.map((code) => {
        const p = byCode.get(code);
        const active = selected === code;
        return (
          <button
            key={code}
            onClick={() => onSelect(active ? null : code)}
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 font-num text-[11px] transition-colors ${
              active
                ? "border-white/40 bg-white/10 text-white"
                : "border-[var(--panel-border-strong)] text-[var(--text-mid)] hover:border-white/30 hover:text-white"
            }`}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: p ? RISK_COLOR[p.risk_level] : "#4b5563" }} />
            {code}
          </button>
        );
      })}
    </div>
  );
}
