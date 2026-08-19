import { useEffect, useRef, useState } from "react";
import type {
  AircraftRisk,
  AirportBriefing,
  Briefing,
  FeatureImportance,
  LiveStates,
  Predictions,
  PredictionsSnapshot,
} from "./types";

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

/** Unlike the other hooks, the endpoint here depends on `code` (which airport is
 * currently selected), so this can't just be usePolling with a fixed path -- it
 * refetches whenever `code` changes and polls on the backend's own cache TTL while a
 * code is selected, going idle (no requests) when nothing is selected. */
export function useAirportBriefing(code: string | null) {
  const [data, setData] = useState<AirportBriefing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!code) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    // clear immediately, not just when code goes null -- otherwise switching directly
    // from one selected airport to another renders the previous one's briefing under
    // the new airport's label for the 1-3s until the new fetch resolves
    setData(null);
    setLoading(true);

    async function tick() {
      try {
        const result = await getJSON<AirportBriefing>(`/briefing/airport?code=${code}`);
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
        if (!cancelled) timer = setTimeout(tick, 45_000);
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [code]);

  return { data, error, loading };
}

/** Depends on `icao24` like useAirportBriefing does, but a 404 here is an ordinary,
 * expected outcome (no aircraft-type data on file for this tail number) rather than a
 * failure -- handled as "no data" (data stays null, error stays null), not surfaced as
 * an error state in the UI. */
export function useAircraftRisk(icao24: string | null) {
  const [data, setData] = useState<AircraftRisk | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!icao24) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    // clear immediately, not just when icao24 goes null -- otherwise clicking straight
    // from one aircraft to another renders the previous one's risk card under the new
    // aircraft's label for the 1-3s until the new fetch resolves
    setData(null);
    setLoading(true);

    async function tick() {
      try {
        const res = await fetch(`/api/aircraft/${icao24}/risk`);
        if (res.status === 404) {
          if (!cancelled) {
            setData(null);
            setError(null);
            setLoading(false);
          }
          return;
        }
        if (!res.ok) throw new Error(`aircraft risk -> ${res.status}`);
        const result = (await res.json()) as AircraftRisk;
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
        if (!cancelled) timer = setTimeout(tick, 30_000);
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [icao24]);

  return { data, error, loading };
}

export function useFeatureImportance() {
  // static per model version -- refetching every 10min just self-heals if the model
  // is retrained during a long-running session, not meant as "live" polling
  return usePolling<{ features: FeatureImportance[] }>("/model/feature-importance", 600_000);
}
