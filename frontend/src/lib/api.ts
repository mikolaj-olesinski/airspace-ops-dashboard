import { useEffect, useRef, useState } from "react";
import type { Briefing, LiveStates, Predictions, PredictionsSnapshot } from "./types";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

/** Polls an endpoint on an interval, keeping the last-good value on error so the UI
 * doesn't flash empty on a transient failure (OpenSky's anonymous tier is not always
 * fast -- see backend/opensky_client.py). */
function usePolling<T>(path: string, intervalMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const result = await getJSON<T>(path);
        if (!cancelled) {
          setData(result);
          setError(null);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      } finally {
        if (!cancelled) {
          timer.current = setTimeout(tick, intervalMs);
        }
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, intervalMs]);

  return { data, error, loading };
}

export function useLiveStates() {
  return usePolling<LiveStates>("/live-states", 12_000);
}

export function usePredictions() {
  return usePolling<Predictions>("/predictions", 30_000);
}

export function useBriefing() {
  // matches the backend's briefing_cache.py TTL -- polling faster wouldn't return
  // anything new anyway
  return usePolling<Briefing>("/briefing", 60_000);
}

export function usePredictionsHistory() {
  // matches predictions_history_cache.py's poll interval
  return usePolling<{ snapshots: PredictionsSnapshot[] }>("/predictions/history", 30_000);
}
