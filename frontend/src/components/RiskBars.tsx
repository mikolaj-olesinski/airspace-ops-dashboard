import type { AirportPrediction, PredictionsSnapshot } from "../lib/types";
import Sparkline from "./Sparkline";
import EmptyState from "./EmptyState";

const RISK_COLOR: Record<string, string> = {
  low: "var(--risk-low)",
  medium: "var(--risk-medium)",
  high: "var(--risk-high)",
};

function trendFor(history: PredictionsSnapshot[], airport: string): number[] {
  return history
    .map((snap) => snap.predictions.find((p) => p.airport === airport)?.risk_score)
    .filter((v): v is number => v != null);
}

export default function RiskBars({
  predictions,
  history = [],
  selectedAirport = null,
  onSelect,
}: {
  predictions: AirportPrediction[];
  history?: PredictionsSnapshot[];
  selectedAirport?: string | null;
  onSelect?: (code: string | null) => void;
}) {
  const sorted = [...predictions].sort((a, b) => b.risk_score - a.risk_score);

  if (sorted.length === 0) {
    return <EmptyState message="waiting for predictions..." variant="loading" />;
  }

  return (
    <div className="flex h-full flex-col justify-start gap-3 overflow-y-auto">
      {sorted.map((p, i) => {
        const active = selectedAirport === p.airport;
        const dimmed = selectedAirport !== null && !active;
        return (
          <button
            key={p.airport}
            type="button"
            onClick={() => onSelect?.(active ? null : p.airport)}
            className={`fade-in flex w-full items-center gap-3 bg-transparent p-0 text-left transition-opacity ${
              dimmed ? "opacity-40" : "opacity-100"
            } ${onSelect ? "cursor-pointer" : ""}`}
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <span className={`w-11 shrink-0 font-num text-xs ${active ? "text-white" : "text-[var(--text-mid)]"}`}>
              {p.airport}
            </span>
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
            <div className="w-10 shrink-0">
              <Sparkline values={trendFor(history, p.airport)} width={40} height={16} color={RISK_COLOR[p.risk_level]} />
            </div>
          </button>
        );
      })}
    </div>
  );
}
