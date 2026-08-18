import { useState } from "react";
import { useBriefing } from "../lib/api";
import { useTypewriter } from "../lib/useTypewriter";
import ChatModal from "./ChatModal";

export default function BriefingPanel() {
  const { data, error, loading } = useBriefing();
  const briefingText = data?.briefing ?? (loading ? "Generating briefing..." : error ? `Briefing unavailable: ${error}` : "");
  const shown = useTypewriter(briefingText);
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="flex h-full flex-col justify-between gap-2">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="text-[13px] leading-relaxed text-[#d1d5db]">
          {shown}
          <span className="ml-[1px] inline-block h-[13px] w-[6px] translate-y-[2px] animate-pulse bg-[#d1d5db]/60" />
        </p>
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-[var(--panel-border)] pt-2">
        <span className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">
          LangGraph ops agent -- Claude Haiku
        </span>
        <button
          onClick={() => setChatOpen(true)}
          className="rounded-full border border-[var(--panel-border-strong)] px-3 py-1 text-[11px] text-[var(--text-mid)] hover:border-[#60a5fa]/50 hover:text-white"
        >
          Open chat →
        </button>
      </div>

      {chatOpen && <ChatModal onClose={() => setChatOpen(false)} />}
    </div>
  );
}
