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

from agent.formatting import weather_line

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

MODEL_NAME = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are an airspace operations assistant. You write short, operational "
    "briefings for air traffic ops staff based on a delay-risk model's live "
    "predictions for a handful of European airports. Write 2-3 sentences of plain "
    "operational language (like an ATC ops desk note, not a data report). Name the "
    "highest-risk airport(s) specifically and explain why using the 'top model "
    "drivers' given for it -- these are the model's own real feature attributions, "
    "not a guess, so cite them directly rather than picking a plausible-sounding "
    "cause yourself. Suggest one concrete monitoring action. Only use numbers you "
    "were given -- never invent one. Plain text only -- no markdown, no bold, no "
    "bullet points."
)

AIRPORT_SYSTEM_PROMPT = (
    "You are an airspace operations assistant writing a focused briefing about ONE "
    "airport for ops staff. You are given that airport's current risk, its top "
    "model-identified risk drivers for this exact prediction (real feature "
    "attributions from the model, not a guess), and its recent risk trend. In 2-3 "
    "sentences total, written as ONE short paragraph (no line breaks), explain WHY "
    "the risk is what it is by citing the drivers given by name and value, plus "
    "whether it's trending up, down, or holding steady, then end with one concrete "
    "monitoring action. Be terse and concrete, like a real ops desk note -- not an "
    "essay. Only use numbers you were given -- never invent one. Plain text only -- "
    "no markdown, no bold, no bullet points."
)


class BriefingState(TypedDict):
    predictions: list[dict]
    context: str
    briefing: str


def collect_context(state: BriefingState) -> BriefingState:
    ranked = sorted(state["predictions"], key=lambda p: p["risk_score"], reverse=True)
    lines = []
    for p in ranked:
        factors = p.get("top_factors") or []
        factors_text = "; ".join(f"{f['label']} ({f['value']}) {f['direction']} risk" for f in factors[:2])
        line = (
            f"- {p['airport']}: risk {round(p['risk_score'] * 100)}% ({p['risk_level']}), "
            f"{p['live_traffic_count']} aircraft nearby, {weather_line(p['weather'])}"
        )
        if factors_text:
            line += f", top model drivers: {factors_text}"
        lines.append(line)
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


def generate_for_airport(prediction: dict, trend: list[int]) -> str:
    """Same purpose as generate(), focused on one airport the user clicked on -- grounds
    the LLM in that prediction's real top_factors (model_service._top_factors, a genuine
    per-prediction SHAP-style attribution) and recent trend instead of the coarser
    "mention a likely factor" framing used for the all-airports briefing. A single LLM
    call rather than its own graph: there's no multi-step state here to justify one, all
    the "reasoning" already happened in the model's own feature attribution."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set (expected in backend/.env)")

    factors = prediction.get("top_factors") or []
    factors_text = "\n".join(f"- {f['label']} ({f['value']}) {f['direction']} risk" for f in factors) or (
        "- no strong individual driver identified (all features near neutral for this prediction)"
    )
    trend_text = (
        f"Risk over roughly the last hour (oldest to newest, %): {', '.join(map(str, trend))}"
        if trend
        else "No trend history yet -- this is one of the first snapshots since startup."
    )

    context = (
        f"Airport: {prediction['airport']}\n"
        f"Current risk: {round(prediction['risk_score'] * 100)}% ({prediction['risk_level']})\n"
        f"Live traffic nearby: {prediction['live_traffic_count']} aircraft\n"
        f"Weather: {weather_line(prediction['weather'])}\n"
        f"Top model-identified risk drivers for this exact prediction:\n{factors_text}\n"
        f"{trend_text}"
    )

    llm = ChatAnthropic(model=MODEL_NAME, max_tokens=200, temperature=0.4)
    messages = [SystemMessage(content=AIRPORT_SYSTEM_PROMPT), HumanMessage(content=context)]
    response = llm.invoke(messages)
    return response.content
