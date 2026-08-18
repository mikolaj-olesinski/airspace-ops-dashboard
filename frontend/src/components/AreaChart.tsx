interface AreaChartProps {
  values: number[];
  height?: number;
  color?: string;
  unit?: string;
}

/** A bigger sibling of Sparkline.tsx -- gridlines and min/max/current labels, sized to
 * fill its container's width responsively via a viewBox instead of a fixed width. */
export default function AreaChart({ values, height = 120, color = "#60a5fa", unit = "" }: AreaChartProps) {
  const width = 600; // viewBox units; actual rendered width is responsive (see svg width="100%")

  if (values.length < 2) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-[var(--text-dim)]">
        collecting data...
      </div>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padX = 8;
  const padY = 10;

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - padX * 2) + padX;
    const y = height - padY - ((v - min) / range) * (height - padY * 2);
    return [x, y] as const;
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${height - padY} L${points[0][0].toFixed(1)},${height - padY} Z`;
  const gridLines = [0.25, 0.5, 0.75];
  const current = values[values.length - 1];

  return (
    <div className="relative h-full w-full">
      <div className="absolute top-0 right-0 flex items-baseline gap-1">
        <span className="font-num text-lg font-semibold text-white">{Math.round(current)}</span>
        <span className="text-[10px] text-[var(--text-dim)]">{unit}</span>
      </div>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="mt-1">
        {gridLines.map((g) => (
          <line
            key={g}
            x1={0}
            x2={width}
            y1={padY + g * (height - padY * 2)}
            y2={padY + g * (height - padY * 2)}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={1}
          />
        ))}
        <path d={areaPath} fill={color} opacity={0.1} stroke="none" />
        <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={2.5} fill={color} />
      </svg>
      <div className="mt-1 flex justify-between text-[9px] text-[var(--text-dim)]">
        <span>min {Math.round(min)}</span>
        <span>max {Math.round(max)}</span>
      </div>
    </div>
  );
}
