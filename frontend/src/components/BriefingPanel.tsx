import { useState } from "react";
import { useAirportBriefing, useBriefing } from "../lib/api";
import { useTypewriter } from "../lib/useTypewriter";
import ChatModal from "./ChatModal";

export default function BriefingPanel({ selectedAirport = null }: { selectedAirport?: string | null }) {
  const general = useBriefing();
  const airport = useAirportBriefing(selectedAirport);

  const { data, error, loading } = selectedAirport ? airport : general;
  const briefingText =
    data?.briefing ??
    (loading
      ? selectedAirport
        ? `Writing a briefing for ${selectedAirport}...`
        : "Generating briefing..."
      : error
        ? `Briefing unavailable: ${error}`
        : "");
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
          {selectedAirport ? `Focused on ${selectedAirport}` : "LangGraph ops agent -- Claude Haiku"}
        </span>
        <button
          onClick={() => setChatOpen(true)}
          className="rounded-full border border-[var(--panel-border-strong)] px-3 py-1 text-[11px] text-[var(--text-mid)] hover:border-[#60a5fa]/50 hover:text-white"
        >
          Open chat →
        </button>
      </div>

      {/* always mounted (never conditionally rendered) so ChatModal's own message
          history and thread_id survive closing and reopening the chat */}
      <ChatModal open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
