"""Caches the LangGraph briefing agent's output so polling the frontend every ~15s
doesn't call the LLM that often -- CLAUDE.md's own plan calls for refreshing the
briefing on a much slower cadence (e.g. every 60s)."""

import time
from typing import Optional

from agent.briefing_agent import generate

CACHE_TTL_S = 60

_cached_text: Optional[str] = None
_cached_at: float = 0.0


def get_briefing(predictions: list[dict]) -> dict:
    global _cached_text, _cached_at
    now = time.time()
    if _cached_text is None or (now - _cached_at) > CACHE_TTL_S:
        _cached_text = generate(predictions)
        _cached_at = now
    return {"briefing": _cached_text, "generated_at": _cached_at}
