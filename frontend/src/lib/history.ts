import { useEffect, useRef, useState } from "react";
import type { Aircraft } from "./types";

export interface Snapshot {
  time: number; // unix seconds, from the backend poll
  aircraft: Aircraft[];
}

const MAX_HISTORY = 300; // matches the backend's live_state_cache.py buffer (~1h)

/** Seeds from the backend's real polled history (GET /history -- see
 * backend/live_state_cache.py) on mount, then keeps appending as new live snapshots
 * arrive. The backend is the source of truth; this just mirrors it client-side so the
 * time-slider has something to scrub through immediately instead of starting empty. */
export function useAircraftHistory(latest: Snapshot | null) {
  const [history, setHistory] = useState<Snapshot[]>([]);
  const lastTime = useRef<number | null>(null);
  const seeded = useRef(false);

  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    fetch("/api/history")
      .then((res) => (res.ok ? res.json() : { snapshots: [] }))
      .then((data: { snapshots: Snapshot[] }) => {
        setHistory(data.snapshots);
        if (data.snapshots.length > 0) {
          lastTime.current = data.snapshots[data.snapshots.length - 1].time;
        }
      })
      .catch(() => {});
  }, []);

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
