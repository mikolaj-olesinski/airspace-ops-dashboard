import { useEffect, useState } from "react";
import type { AirportPrediction } from "../lib/types";

// Placeholder copy until Phase 4 (LangGraph briefing agent) is wired up to a real
// /briefing endpoint. Picking the current top-risk airport keeps this at least
// grounded in real live data rather than a fully static string.
function placeholderBriefing(top: AirportPrediction | undefined): string {
  if (!top) return "Waiting for live predictions...";
  const pct = Math.round(top.risk_score * 100);
  return (
    `Sector ${top.airport}: elevated delay risk at ${pct}% over the next window. ` +
    `Live traffic density ${top.live_traffic_count} aircraft nearby, wind ${top.weather.wind_speed_10m ?? "n/a"} km/h. ` +
    `Recommend monitoring departure sequencing.`
  );
}

function useTypewriter(text: string, speedMs = 18) {
  const [shown, setShown] = useState("");
  useEffect(() => {
    setShown("");
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, speedMs);
    return () => clearInterval(id);
  }, [text, speedMs]);
  return shown;
}

export default function BriefingPanel({ predictions }: { predictions: AirportPrediction[] }) {
  const top = [...predictions].sort((a, b) => b.risk_score - a.risk_score)[0];
  const text = placeholderBriefing(top);
  const shown = useTypewriter(text);

  return (
    <div className="flex h-full flex-col justify-between">
      <p className="text-[13px] leading-relaxed text-[#d1d5db]">
        {shown}
        <span className="ml-[1px] inline-block h-[13px] w-[6px] translate-y-[2px] animate-pulse bg-[#d1d5db]/60" />
      </p>
      <span className="mt-3 text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">
        LLM ops agent -- Phase 4 (not yet live)
      </span>
    </div>
  );
}
