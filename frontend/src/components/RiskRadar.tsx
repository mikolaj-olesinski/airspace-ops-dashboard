import type { AirportPrediction } from "../lib/types";
import EmptyState from "./EmptyState";

const RISK_COLOR: Record<string, string> = {
  low: "#d4d4d8",
  medium: "#f5a623",
  high: "#f0563a",
};

export default function RiskRadar({
  predictions,
  selectedAirport = null,
  onSelect,
}: {
  predictions: AirportPrediction[];
  selectedAirport?: string | null;
  onSelect?: (code: string | null) => void;
}) {
  const size = 220;
  const center = size / 2;
  const maxR = size / 2 - 28;
  const n = predictions.length;
  const rings = [0.25, 0.5, 0.75, 1];

  const angleFor = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pointAt = (i: number, frac: number) => {
    const a = angleFor(i);
    return [center + Math.cos(a) * maxR * frac, center + Math.sin(a) * maxR * frac] as const;
  };

  if (n === 0) {
    return <EmptyState message="waiting for predictions..." variant="loading" />;
  }

  const dataPoints = predictions.map((p, i) => pointAt(i, Math.max(0.06, p.risk_score)));
  const dataPath = dataPoints.map((pt, i) => `${i === 0 ? "M" : "L"}${pt[0]},${pt[1]}`).join(" ") + "Z";

  return (
    <svg width={size} height={size} className="mx-auto">
      {rings.map((r) => {
        const pts = predictions.map((_, i) => pointAt(i, r).join(",")).join(" ");
        return <polygon key={r} points={pts} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={1} />;
      })}
      {predictions.map((_, i) => {
        const [x, y] = pointAt(i, 1);
        return <line key={i} x1={center} y1={center} x2={x} y2={y} stroke="rgba(255,255,255,0.07)" strokeWidth={1} />;
      })}

      <path d={dataPath} fill="rgba(229,231,235,0.08)" stroke="rgba(229,231,235,0.5)" strokeWidth={1.5} />

      {predictions.map((p, i) => {
        const [dx, dy] = pointAt(i, Math.max(0.06, p.risk_score));
        const [lx, ly] = pointAt(i, 1.22);
        const active = selectedAirport === p.airport;
        const dimmed = selectedAirport !== null && !active;
        const select = () => onSelect?.(active ? null : p.airport);
        return (
          <g
            key={p.airport}
            role={onSelect ? "button" : undefined}
            tabIndex={onSelect ? 0 : undefined}
            aria-label={onSelect ? `${p.airport}, ${Math.round(p.risk_score * 100)}% risk` : undefined}
            aria-pressed={onSelect ? active : undefined}
            className={onSelect ? "radar-node cursor-pointer" : undefined}
            onClick={onSelect ? select : undefined}
            onKeyDown={
              onSelect
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      select();
                    }
                  }
                : undefined
            }
          >
            <circle
              cx={dx}
              cy={dy}
              r={active ? 5 : 3}
              fill={RISK_COLOR[p.risk_level]}
              opacity={dimmed ? 0.35 : 1}
              stroke={active ? "#ffffff" : "none"}
              strokeWidth={active ? 1.5 : 0}
            />
            <text
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="middle"
              className="font-num"
              fontSize={10}
              fill={active ? "#ffffff" : "var(--text-mid)"}
              opacity={dimmed ? 0.5 : 1}
            >
              {p.airport}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
