import type { AirportPrediction } from "../lib/types";

const RISK_COLOR: Record<string, string> = {
  low: "var(--risk-low)",
  medium: "var(--risk-medium)",
  high: "var(--risk-high)",
};

export default function RiskBars({ predictions }: { predictions: AirportPrediction[] }) {
  const sorted = [...predictions].sort((a, b) => b.risk_score - a.risk_score);
  return (
    <div className="flex h-full flex-col justify-center gap-3">
      {sorted.map((p, i) => (
        <div key={p.airport} className="fade-in flex items-center gap-3" style={{ animationDelay: `${i * 40}ms` }}>
          <span className="w-11 shrink-0 font-num text-xs text-[var(--text-mid)]">{p.airport}</span>
          <div className="h-[6px] flex-1 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.round(p.risk_score * 100)}%`,
                background: RISK_COLOR[p.risk_level],
                transition: "width 0.7s ease-out",
              }}
            />
          </div>
          <span className="w-10 shrink-0 text-right font-num text-xs text-[var(--text-mid)]">
            {Math.round(p.risk_score * 100)}%
          </span>
        </div>
      ))}
    </div>
  );
}
