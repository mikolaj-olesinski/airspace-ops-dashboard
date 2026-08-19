import { useEffect, useState } from "react";
import type { Snapshot } from "../lib/history";

function relativeLabel(snapshot: Snapshot, latest: Snapshot | null): string {
  if (!latest) return "--:--";
  const deltaS = Math.max(0, Math.round(latest.time - snapshot.time));
  const m = Math.floor(deltaS / 60);
  const s = deltaS % 60;
  return deltaS === 0 ? "LIVE" : `-${m}:${String(s).padStart(2, "0")}`;
}

interface TimeSliderProps {
  history: Snapshot[];
  scrubIndex: number | null; // null == pinned to live (latest)
  playing: boolean;
  onScrub: (index: number) => void;
  onTogglePlay: () => void;
  onGoLive: () => void;
  /** the backend's actual OpenSky poll cadence -- drives a "next update in Xs"
   * countdown next to the LIVE badge, so the real (credit-budget-limited) ~90s cadence
   * reads as an intentional, visible schedule instead of the UI just looking stuck. */
  pollIntervalS?: number;
}

export default function TimeSlider({
  history,
  scrubIndex,
  playing,
  onScrub,
  onTogglePlay,
  onGoLive,
  pollIntervalS,
}: TimeSliderProps) {
  const [nowS, setNowS] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNowS(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);

  if (history.length < 2) return null;

  const latest = history[history.length - 1];
  const maxIndex = history.length - 1;
  const index = scrubIndex ?? maxIndex;
  const isLive = scrubIndex === null;
  const current = history[index];
  const remainingS = pollIntervalS != null ? Math.max(0, Math.round(pollIntervalS - (nowS - latest.time))) : null;

  return (
    <div className="tick-corners absolute inset-x-3 bottom-3 flex items-center gap-3 border border-[var(--panel-border-strong)] bg-[#0a0b0cf0] px-3 py-2 backdrop-blur-sm">
      <button
        onClick={onTogglePlay}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--panel-border-strong)] text-[10px] text-[#d1d5db] hover:border-white/40"
        title={playing ? "Pause" : "Play"}
      >
        {playing ? "❚❚" : "▶"}
      </button>

      <input
        type="range"
        min={0}
        max={maxIndex}
        value={index}
        onChange={(e) => onScrub(Number(e.target.value))}
        className="h-[3px] flex-1 cursor-pointer appearance-none rounded-full bg-white/10 accent-[#60a5fa]"
      />

      <button
        onClick={onGoLive}
        className="flex shrink-0 items-center gap-1.5 font-num text-[10px] uppercase tracking-[0.1em] text-[var(--text-mid)] hover:text-white"
        title={isLive && remainingS != null ? "OpenSky's free tier caps how often positions can refresh -- see README" : undefined}
      >
        {isLive && <span className="live-dot h-[5px] w-[5px] rounded-full bg-emerald-400" />}
        {isLive && remainingS != null
          ? remainingS > 0
            ? `LIVE · next in ${remainingS}s`
            : "LIVE · updating..."
          : relativeLabel(current, latest)}
      </button>
    </div>
  );
}
