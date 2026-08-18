import { useEffect, useRef, useState } from "react";
import type { Aircraft } from "./types";

export interface Snapshot {
  time: number; // unix seconds, from the backend poll
  aircraft: Aircraft[];
}

const MAX_HISTORY = 60; // ~12 min of buffer at the 12s poll interval

/** Accumulates live-state snapshots into a rolling in-memory buffer as they arrive.
 * There's no server-side history (OpenSky's free tier only gives a live snapshot), so
 * this only covers time since the page was opened -- not true historical replay. */
export function useAircraftHistory(latest: Snapshot | null) {
  const [history, setHistory] = useState<Snapshot[]>([]);
  const lastTime = useRef<number | null>(null);

  useEffect(() => {
    if (!latest || latest.time === lastTime.current) return;
    lastTime.current = latest.time;
    setHistory((prev) => {
      const next = [...prev, latest];
      return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
    });
  }, [latest]);

  return history;
}
