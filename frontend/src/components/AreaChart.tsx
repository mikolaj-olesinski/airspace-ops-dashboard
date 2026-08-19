import { useRef, useState } from "react";
import EmptyState from "./EmptyState";

interface AreaChartProps {
  values: number[];
  /** unix seconds per value, same length/order as `values` -- drives the x-axis end
   * labels and the hover tooltip's time. Falls back to plain min/max labels without it. */
  timestamps?: number[];
  height?: number;
  color?: string;
  unit?: string;
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** A bigger sibling of Sparkline.tsx -- gridlines, a hover tooltip (value + time under
 * the cursor), and x-axis time labels so it's clear what's actually being plotted, sized
 * to fill its container's width responsively via a viewBox instead of a fixed width. */
export default function AreaChart({ values, timestamps, height = 120, color = "#60a5fa", unit = "" }: AreaChartProps) {
  const width = 600; // viewBox units; actual rendered width is responsive (see svg width="100%")
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (values.length < 2) {
    return <EmptyState message="collecting data..." variant="loading" />;
  }

  const dataMin = Math.min(...values);
  const max = Math.max(...values);
  // anchored at 0, not at the window's own local min: with a floating min/max scale,
  // whatever the lowest visible point happens to be always gets drawn at the very
  // bottom of the chart -- a completely ordinary dip (e.g. 428 -> 368) reads as
  // "dropping to zero" even though it isn't. Anchoring at 0 makes the line's height
  // actually proportional to the real value.
  const range = max || 1;
  const padX = 8;
  const padY = 10;

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - padX * 2) + padX;
    const y = height - padY - (v / range) * (height - padY * 2);
    return [x, y] as const;
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${height - padY} L${points[0][0].toFixed(1)},${height - padY} Z`;
  const gridLines = [0.25, 0.5, 0.75];
  const current = values[values.length - 1];

  function handleMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const relX = ((e.clientX - rect.left) / rect.width) * width;
    const frac = Math.min(1, Math.max(0, (relX - padX) / (width - padX * 2)));
    setHoverIdx(Math.round(frac * (values.length - 1)));
  }

  const hoverPoint = hoverIdx != null ? points[hoverIdx] : null;
  const hoverValue = hoverIdx != null ? values[hoverIdx] : null;
  const hoverTime = hoverIdx != null && timestamps ? timestamps[hoverIdx] : null;
  // keep the tooltip box on-screen instead of running off either edge of the chart
  const tooltipLeftPct = hoverPoint ? (Math.min(Math.max(hoverPoint[0], 34), width - 34) / width) * 100 : 0;

  return (
    <div className="relative h-full w-full">
      <div className="absolute top-0 right-0 flex items-baseline gap-1">
        <span className="font-num text-lg font-semibold text-white">{Math.round(hoverValue ?? current)}</span>
        <span className="text-[10px] text-[var(--text-dim)]">{unit}</span>
      </div>
      <svg
        ref={svgRef}
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="mt-1 cursor-crosshair"
        onPointerMove={handleMove}
        onPointerLeave={() => setHoverIdx(null)}
      >
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

        {hoverPoint && (
          <g>
            <line
              x1={hoverPoint[0]}
              x2={hoverPoint[0]}
              y1={padY}
              y2={height - padY}
              stroke="rgba(255,255,255,0.25)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <circle cx={hoverPoint[0]} cy={hoverPoint[1]} r={3.5} fill="#fff" stroke={color} strokeWidth={1.5} />
          </g>
        )}
      </svg>

      {hoverPoint && hoverValue != null && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-[calc(100%+6px)] whitespace-nowrap rounded border border-[var(--panel-border-strong)] bg-[#0a0b0cf5] px-2 py-1 text-[10px] shadow-lg"
          style={{ left: `${tooltipLeftPct}%`, top: `${(hoverPoint[1] / height) * 100}%` }}
        >
          <div className="font-num font-semibold text-white">
            {Math.round(hoverValue)} {unit}
          </div>
          {hoverTime != null && <div className="text-[var(--text-dim)]">{formatTime(hoverTime)}</div>}
        </div>
      )}

      <div className="mt-1 flex justify-between text-[9px] text-[var(--text-dim)]">
        {timestamps ? (
          <>
            <span>{formatTime(timestamps[0])}</span>
            <span>{formatTime(timestamps[timestamps.length - 1])} · now</span>
          </>
        ) : (
          <>
            <span>min {Math.round(dataMin)}</span>
            <span>max {Math.round(max)}</span>
          </>
        )}
      </div>
    </div>
  );
}
