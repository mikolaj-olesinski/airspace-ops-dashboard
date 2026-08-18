"""LangGraph agent that turns per-airport delay-risk predictions into a short,
human-readable ops briefing. Two nodes, per CLAUDE.md's Phase 4 plan:
  collect_context   -- ranks airports by risk and formats the raw prediction data
                        into a compact summary for the prompt
  generate_briefing -- calls the LLM with that summary, asking for 2-3 operational
                        sentences (the kind an ops desk note would actually read)
"""

import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

MODEL_NAME = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are an airspace operations assistant. You write short, operational "
    "briefings for air traffic ops staff based on a delay-risk model's live "
    "predictions for a handful of European airports. Write 2-3 sentences of plain "
    "operational language (like an ATC ops desk note, not a data report). Name the "
    "highest-risk airport(s) specifically, mention a likely contributing factor from "
    "the data given (traffic density or weather), and suggest one concrete "
    "monitoring action. Only use numbers you were given -- never invent one. "
    "Plain text only -- no markdown, no bold, no bullet points."
)


class BriefingState(TypedDict):
    predictions: list[dict]
    context: str
    briefing: str


def collect_context(state: BriefingState) -> BriefingState:
    ranked = sorted(state["predictions"], key=lambda p: p["risk_score"], reverse=True)
    lines = []
    for p in ranked:
        w = p["weather"]
        lines.append(
            f"- {p['airport']}: risk {round(p['risk_score'] * 100)}% ({p['risk_level']}), "
            f"{p['live_traffic_count']} aircraft nearby, wind {w['wind_speed_10m']} km/h, "
            f"temp {w['temperature_2m']}C, precip {w['precipitation']} mm"
        )
    return {**state, "context": "\n".join(lines)}


def generate_briefing(state: BriefingState) -> BriefingState:
    llm = ChatAnthropic(model=MODEL_NAME, max_tokens=200, temperature=0.4)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Current predictions (highest risk first):\n{state['context']}"),
    ]
    response = llm.invoke(messages)
    return {**state, "briefing": response.content}


def build_graph():
    graph = StateGraph(BriefingState)
    graph.add_node("collect_context", collect_context)
    graph.add_node("generate_briefing", generate_briefing)
    graph.set_entry_point("collect_context")
    graph.add_edge("collect_context", "generate_briefing")
    graph.add_edge("generate_briefing", END)
    return graph.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def generate(predictions: list[dict]) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set (expected in backend/.env)")
    result = get_graph().invoke({"predictions": predictions, "context": "", "briefing": ""})
    return result["briefing"]
