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

interface QA {
  question: string;
  answer: string;
}

export default function BriefingPanel() {
  const { data, error, loading } = useBriefing();
  const briefingText = data?.briefing ?? (loading ? "Generating briefing..." : error ? `Briefing unavailable: ${error}` : "");

  const [qa, setQa] = useState<QA | null>(null);
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState("");

  const shownBriefing = useTypewriter(qa ? "" : briefingText);
  const shownAnswer = useTypewriter(qa?.answer ?? "");

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    setQuestion("");
    try {
      const res = await fetch(`/api/agent/ask?q=${encodeURIComponent(q)}`);
      const body = await res.json();
      setQa({ question: q, answer: res.ok ? body.answer : `Error: ${body.detail ?? res.status}` });
    } catch (err) {
      setQa({ question: q, answer: `Error: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex h-full flex-col justify-between gap-2">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {qa ? (
          <div className="fade-in">
            <div className="flex items-start justify-between gap-2">
              <span className="text-[12px] font-medium text-[#60a5fa]">Q: {qa.question}</span>
              <button onClick={() => setQa(null)} className="shrink-0 text-[var(--text-dim)] hover:text-white">
                ✕
              </button>
            </div>
            <p className="mt-1 text-[13px] leading-relaxed text-[#d1d5db]">
              {shownAnswer}
              <span className="ml-[1px] inline-block h-[13px] w-[6px] translate-y-[2px] animate-pulse bg-[#d1d5db]/60" />
            </p>
          </div>
        ) : (
          <p className="text-[13px] leading-relaxed text-[#d1d5db]">
            {shownBriefing}
            <span className="ml-[1px] inline-block h-[13px] w-[6px] translate-y-[2px] animate-pulse bg-[#d1d5db]/60" />
          </p>
        )}
      </div>

      <form onSubmit={handleAsk} className="flex shrink-0 items-center gap-2 border-t border-[var(--panel-border)] pt-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask the ops agent (e.g. a callsign, or 'riskiest airport')"
          disabled={asking}
          className="flex-1 bg-transparent text-[12px] text-[#d1d5db] placeholder:text-[var(--text-dim)] focus:outline-none"
        />
        <button
          type="submit"
          disabled={asking || !question.trim()}
          className="shrink-0 text-[11px] uppercase tracking-[0.1em] text-[var(--text-mid)] hover:text-white disabled:opacity-40"
        >
          {asking ? "..." : "Ask"}
        </button>
      </form>
      <span className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-dim)]">
        LangGraph ops agent -- Claude Haiku
      </span>
    </div>
  );
}
