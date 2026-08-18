import type { AirportPrediction } from "../lib/types";

const RISK_COLOR: Record<string, string> = {
  low: "#d4d4d8",
  medium: "#f5a623",
  high: "#f0563a",
};

export default function RiskRadar({ predictions }: { predictions: AirportPrediction[] }) {
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
        const [x, y] = pointAt(i, Math.max(0.06, p.risk_score));
        return <circle key={p.airport} cx={x} cy={y} r={3} fill={RISK_COLOR[p.risk_level]} />;
      })}

      {predictions.map((p, i) => {
        const [x, y] = pointAt(i, 1.22);
        return (
          <text
            key={p.airport}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="font-num"
            fontSize={10}
            fill="var(--text-mid)"
          >
            {p.airport}
          </text>
        );
      })}
    </svg>
  );
}
