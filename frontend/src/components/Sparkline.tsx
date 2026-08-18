interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  fillOpacity?: number;
}

export default function Sparkline({ values, width = 200, height = 36, color = "#60a5fa", fillOpacity = 0.12 }: SparklineProps) {
  if (values.length < 2) {
    return (
      <svg width={width} height={height}>
        {width >= 80 && (
          <text x={width / 2} y={height / 2} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill="var(--text-dim)">
            not enough data yet
          </text>
        )}
      </svg>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 3;

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - pad * 2) + pad;
    const y = height - pad - ((v - min) / range) * (height - pad * 2);
    return [x, y] as const;
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${height - pad} L${points[0][0].toFixed(1)},${height - pad} Z`;

  return (
    <svg width={width} height={height}>
      <path d={areaPath} fill={color} opacity={fillOpacity} stroke="none" />
      <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={2} fill={color} />
    </svg>
  );
}
