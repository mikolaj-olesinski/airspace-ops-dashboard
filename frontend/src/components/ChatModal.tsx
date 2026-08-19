import { useEffect, useRef, useState } from "react";
import { useTypewriter } from "../lib/useTypewriter";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const STARTERS = [
  "what's the riskiest airport right now",
  "tell me about the highest aircraft nearby",
  "is Munich's risk trending up or down",
];

// generic ops-desk follow-ups shown after the latest answer, not personalized to its
// content (that would need an extra LLM call) but still a genuinely useful "what would
// I ask next" nudge -- the agent resolves "that"/"it" against the conversation itself.
const FOLLOWUPS = ["why is that?", "check the trend", "any other airports I should watch?"];

function AssistantBubble({ content, isLatest }: { content: string; isLatest: boolean }) {
  const shown = useTypewriter(content, isLatest ? 14 : 0);
  return (
    <div className="fade-in max-w-[75%] self-start rounded-lg rounded-bl-sm border border-[var(--panel-border)] bg-[#111214] px-4 py-3 text-[14px] leading-relaxed text-[#d1d5db]">
      {shown}
      {isLatest && shown.length < content.length && (
        <span className="ml-[1px] inline-block h-[14px] w-[6px] translate-y-[2px] animate-pulse bg-[#d1d5db]/60" />
      )}
    </div>
  );
}

export default function ChatModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  // deliberately kept mounted even while closed (see BriefingPanel) so this state --
  // message history, thread_id -- survives closing and reopening the chat instead of
  // starting over every time
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const threadId = useRef(crypto.randomUUID());
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [open, messages, asking]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || asking) return;
    setInput("");
    setAsking(true);
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: q }]);
    try {
      const res = await fetch(`/api/agent/ask?q=${encodeURIComponent(q)}&thread_id=${threadId.current}`);
      const body = await res.json();
      const answer = res.ok ? body.answer : `Error: ${body.detail ?? res.status}`;
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", content: answer }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "assistant", content: `Error: ${err instanceof Error ? err.message : String(err)}` },
      ]);
    } finally {
      setAsking(false);
    }
  }

  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  return (
    <div className={`fixed inset-0 z-50 flex-col bg-[#08090af5] backdrop-blur-sm ${open ? "flex" : "hidden"}`}>
      <div className="flex items-center justify-between border-b border-[var(--panel-border)] px-6 py-4">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-semibold tracking-[0.02em] text-white">OPS AGENT</h2>
          <span className="text-[11px] text-[var(--text-dim)]">LangGraph &middot; Claude Haiku &middot; live tools</span>
        </div>
        <button onClick={onClose} className="text-[var(--text-mid)] hover:text-white" aria-label="Close chat">
          ✕ <span className="ml-1 text-[10px] uppercase tracking-[0.1em]">esc</span>
        </button>
      </div>

      <div ref={scrollRef} className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-3 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <p className="text-[13px] text-[var(--text-dim)]">
              Ask about live risk, a specific aircraft, or a trend. The agent calls real tools against
              live data -- it doesn't guess.
            </p>
            <div className="flex flex-col gap-2">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-[var(--panel-border-strong)] px-4 py-2 text-[12px] text-[var(--text-mid)] hover:border-white/40 hover:text-white"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) =>
          m.role === "user" ? (
            <div
              key={m.id}
              className="fade-in max-w-[75%] self-end rounded-lg rounded-br-sm bg-[#1d3a5f] px-4 py-3 text-[14px] text-white"
            >
              {m.content}
            </div>
          ) : (
            <AssistantBubble key={m.id} content={m.content} isLatest={m.id === lastAssistantId} />
          ),
        )}

        {asking && (
          <div className="flex gap-1 self-start px-4 py-3">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 rounded-full bg-[var(--text-dim)]"
                style={{ animation: "pulse-dot 1.2s ease-in-out infinite", animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        )}

        {!asking && lastAssistantId && (
          <div className="fade-in flex flex-wrap gap-2 self-start pl-1">
            {FOLLOWUPS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-[var(--panel-border)] px-3 py-1 text-[11px] text-[var(--text-dim)] hover:border-white/30 hover:text-[var(--text-mid)]"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mx-auto flex w-full max-w-3xl shrink-0 items-center gap-3 border-t border-[var(--panel-border)] px-6 py-4"
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the ops agent..."
          disabled={asking}
          className="flex-1 rounded-lg border border-[var(--panel-border)] bg-[#111214] px-4 py-2.5 text-[14px] text-white placeholder:text-[var(--text-dim)] focus:border-[#60a5fa]/50 focus:outline-none"
        />
        <button
          type="submit"
          disabled={asking || !input.trim()}
          className="shrink-0 rounded-lg bg-[#60a5fa] px-4 py-2.5 text-[12px] font-medium text-[#08090a] hover:bg-[#7db4fb] disabled:opacity-30"
        >
          Send
        </button>
      </form>
    </div>
  );
}
