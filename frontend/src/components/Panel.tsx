import type { ReactNode } from "react";

interface PanelProps {
  label: string;
  sublabel?: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export default function Panel({ label, sublabel, children, className = "", bodyClassName = "" }: PanelProps) {
  return (
    <div
      className={`tick-corners panel-hover relative flex flex-col border border-[var(--panel-border)] bg-[#0a0b0c] ${className}`}
    >
      <div className="flex flex-nowrap items-baseline justify-between gap-2 overflow-hidden px-4 pt-3 pb-2">
        <span className="truncate text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--text-mid)]">
          {label}
        </span>
        {sublabel && (
          <span className="shrink-0 truncate font-num text-[11px] text-[var(--text-dim)]">{sublabel}</span>
        )}
      </div>
      <div className={`min-h-0 flex-1 px-4 pb-4 ${bodyClassName}`}>{children}</div>
    </div>
  );
}
