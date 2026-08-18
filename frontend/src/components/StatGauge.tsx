import { useEffect, useRef, useState } from "react";

interface StatGaugeProps {
  value: number;
  max: number;
  label: string;
  /** static text, used as-is if `format` isn't given (no count-up animation) */
  displayValue?: string;
  /** formats the animated numeric value on each frame -- pass this instead of
   * displayValue to get a count-up/down animation when `value` changes */
  format?: (animatedValue: number) => string;
  color?: string;
  size?: number;
}

function useAnimatedNumber(target: number, durationMs = 600) {
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    const to = target;
    if (from === to) return;
    const start = performance.now();

    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 2);
      setDisplay(from + (to - from) * eased);
      if (t < 1) {
        frameRef.current = requestAnimationFrame(step);
      } else {
        fromRef.current = to;
      }
    };
    frameRef.current = requestAnimationFrame(step);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);

  return display;
}

export default function StatGauge({
  value,
  max,
  label,
  displayValue,
  format,
  color = "#e5e7eb",
  size = 140,
}: StatGaugeProps) {
  const strokeWidth = 6;
  const radius = size / 2 - strokeWidth * 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(1, max > 0 ? value / max : 0));
  const dash = circumference * pct;
  const center = size / 2;

  const animated = useAnimatedNumber(value);
  const text = format ? format(animated) : (displayValue ?? String(Math.round(animated)));

  return (
    <div className="flex h-full flex-col items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          style={{ transition: "stroke-dasharray 0.6s ease-out" }}
        />
      </svg>
      <div className="-mt-[86px] flex flex-col items-center">
        <span className="font-num text-2xl font-semibold text-white">{text}</span>
        <span className="mt-1 text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">
          {label}
        </span>
      </div>
    </div>
  );
}
