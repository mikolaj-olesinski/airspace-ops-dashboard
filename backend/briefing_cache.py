"""Caches the LangGraph briefing agent's output so polling the frontend every ~15s
doesn't call the LLM that often -- CLAUDE.md's own plan calls for refreshing the
briefing on a much slower cadence (e.g. every 60s)."""

import time
from typing import Optional

from agent.briefing_agent import generate, generate_for_airport

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


# shorter TTL than the all-airports briefing: this is generated on-demand right after a
# user clicks an airport, so it should refresh faster than the passively-polled one
AIRPORT_CACHE_TTL_S = 45
_airport_cache: dict[str, tuple[str, float]] = {}


def get_airport_briefing(prediction: dict, trend: list[int]) -> dict:
    code = prediction["airport"]
    now = time.time()
    cached = _airport_cache.get(code)
    if cached is None or (now - cached[1]) > AIRPORT_CACHE_TTL_S:
        cached = (generate_for_airport(prediction, trend), now)
        _airport_cache[code] = cached
    text, generated_at = cached
    return {"briefing": text, "generated_at": generated_at, "airport": code}
