"""A LangGraph ReAct agent that answers free-text questions about the live airspace
picture -- "what's the riskiest airport right now", "tell me about flight DLH2MM",
"is EDDM's risk trending up" -- by calling the tools in tools.py rather than being fed
a fixed context blob like briefing_agent.py's briefing does. This is the same live
caches, just exposed as callable tools so the model decides what it needs and can
chain lookups (e.g. find an aircraft, then check its departure airport's risk).

Uses a checkpointer (LangGraph's built-in conversation memory) keyed by thread_id, so
follow-ups like "check the trend for that one" resolve against the actual prior
exchange instead of each question being answered in isolation. thread_id comes from
the frontend (one per browser chat session -- see ChatModal.tsx); MemorySaver keeps
everything in-process memory, fine for a single-instance local demo, not meant to
survive a restart.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agent.tools import TOOLS

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

MODEL_NAME = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are an airspace operations assistant with live tools for current delay-risk "
    "predictions, live aircraft lookups, and airport risk trends. Answer briefly and "
    "concretely, like an ops desk colleague, not a report. Always use a tool to check "
    "live data before answering questions about current conditions, specific flights, "
    "or trends -- never guess or invent numbers. When asked why an airport's risk is "
    "what it is, use the top model drivers returned by get_current_predictions "
    "(real per-prediction feature attributions) rather than speculating. If a tool "
    "finds nothing, say so "
    "plainly rather than making something up. You're in an ongoing conversation, so "
    "resolve follow-ups ('check that for me', 'and Munich?') against what was already "
    "discussed instead of asking the user to repeat themselves. Plain text only -- no "
    "markdown, no bold, no bullet points."
)

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        llm = ChatAnthropic(model=MODEL_NAME, max_tokens=400, temperature=0.2)
        _agent = create_react_agent(llm, TOOLS, prompt=SYSTEM_PROMPT, checkpointer=MemorySaver())
    return _agent


def ask(question: str, thread_id: str = "default") -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set (expected in backend/.env)")
    config = {"configurable": {"thread_id": thread_id}}
    result = get_agent().invoke({"messages": [{"role": "user", "content": question}]}, config=config)
    return result["messages"][-1].content
