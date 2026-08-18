import { useEffect, useState } from "react";

export default function Header({ isLive }: { isLive: boolean }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="flex items-center justify-between border-b border-[var(--panel-border)] px-5 py-3">
      <div className="flex items-baseline gap-3">
        <h1 className="text-sm font-semibold tracking-[0.02em] text-white">
          LIVE AIRSPACE OPS
        </h1>
        <span className="text-[11px] text-[var(--text-dim)]">mini-Prescience</span>
      </div>
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2">
          <span
            className={`live-dot h-[6px] w-[6px] rounded-full ${isLive ? "bg-emerald-400" : "bg-red-500"}`}
          />
          <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-mid)]">
            {isLive ? "Live" : "Reconnecting"}
          </span>
        </div>
        <span className="font-num text-[11px] text-[var(--text-dim)]">
          {now.toUTCString().slice(17, 25)} UTC
        </span>
      </div>
    </header>
  );
}
