import type { PredictionsSnapshot } from "../lib/types";

interface Delta {
  airport: string;
  from: number;
  to: number;
  deltaPts: number;
}

/** Compares the two most recent prediction snapshots (predictions_history_cache.py
 * polls every 30s) and surfaces what actually moved -- real deltas, not a model
 * "learning live" (there's no ground-truth label to learn from in real time, see
 * README), but a direct, honest answer to "what's influencing the risk right now". */
function computeDeltas(history: PredictionsSnapshot[]): Delta[] {
  if (history.length < 2) return [];
  const prev = history[history.length - 2];
  const curr = history[history.length - 1];
  const prevByAirport = new Map(prev.predictions.map((p) => [p.airport, p.risk_score]));

  const deltas: Delta[] = [];
  for (const p of curr.predictions) {
    const before = prevByAirport.get(p.airport);
    if (before == null) continue;
    const from = Math.round(before * 100);
    const to = Math.round(p.risk_score * 100);
    if (from !== to) deltas.push({ airport: p.airport, from, to, deltaPts: to - from });
  }
  return deltas.sort((a, b) => Math.abs(b.deltaPts) - Math.abs(a.deltaPts));
}

export default function LiveDeltas({ history }: { history: PredictionsSnapshot[] }) {
  const deltas = computeDeltas(history);
  if (deltas.length === 0) return null;

  return (
    <div className="flex shrink-0 items-center gap-4 overflow-x-auto border-b border-[var(--panel-border)] px-5 py-1.5">
      <span className="shrink-0 text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">Just changed</span>
      {deltas.slice(0, 6).map((d) => (
        <span key={d.airport} className="fade-in flex shrink-0 items-center gap-1 font-num text-[11px]">
          <span className={d.deltaPts > 0 ? "text-[var(--risk-high)]" : "text-[var(--risk-low)]"}>{d.deltaPts > 0 ? "▲" : "▼"}</span>
          <span className="text-white">{d.airport}</span>
          <span className="text-[var(--text-dim)]">
            {d.from}%→{d.to}%
          </span>
        </span>
      ))}
    </div>
  );
}
