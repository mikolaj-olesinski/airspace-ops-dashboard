import { useEffect, useState } from "react";
import { useBriefing } from "../lib/api";

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

export default function BriefingPanel() {
  const { data, error, loading } = useBriefing();
  const text = data?.briefing ?? (loading ? "Generating briefing..." : error ? `Briefing unavailable: ${error}` : "");
  const shown = useTypewriter(text);

  return (
    <div className="flex h-full flex-col justify-between">
      <p className="text-[13px] leading-relaxed text-[#d1d5db]">
        {shown}
        <span className="ml-[1px] inline-block h-[13px] w-[6px] translate-y-[2px] animate-pulse bg-[#d1d5db]/60" />
      </p>
      <span className="mt-3 text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">
        LangGraph ops agent -- Claude Haiku
      </span>
    </div>
  );
}
