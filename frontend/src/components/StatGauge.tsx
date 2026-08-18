interface StatGaugeProps {
  value: number;
  max: number;
  label: string;
  displayValue: string;
  color?: string;
  size?: number;
}

export default function StatGauge({
  value,
  max,
  label,
  displayValue,
  color = "#e5e7eb",
  size = 140,
}: StatGaugeProps) {
  const strokeWidth = 6;
  const radius = size / 2 - strokeWidth * 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(1, max > 0 ? value / max : 0));
  const dash = circumference * pct;
  const center = size / 2;

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
        <span className="font-num text-2xl font-semibold text-white">{displayValue}</span>
        <span className="mt-1 text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">
          {label}
        </span>
      </div>
    </div>
  );
}
