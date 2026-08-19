"""Background poller that periodically snapshots /predictions' output into a rolling
history buffer, so the frontend can show a risk-over-time sparkline when an airport is
selected -- not just the single current value. Runs on its own (slower) interval from
live_state_cache.py's OpenSky poll, since weather barely changes minute to minute and
there's no need to recompute predictions as often as aircraft positions.
"""

import asyncio
from collections import deque

from backend.live_state_cache import get_latest
from backend.predictions_service import compute_predictions

POLL_INTERVAL_S = 30
HISTORY_MAXLEN = 120  # ~1h of history at one snapshot per POLL_INTERVAL_S

_history: deque = deque(maxlen=HISTORY_MAXLEN)


def get_predictions_history() -> list[dict]:
    return list(_history)


def get_latest_predictions() -> list[dict] | None:
    """Just the most recent snapshot's per-airport predictions (with their already-
    fetched live weather/METAR/traffic embedded) -- lets a one-off computation like
    aircraft_risk_service.compute_aircraft_risk() reuse that context instead of
    re-fetching live sources for a single click."""
    return _history[-1]["predictions"] if _history else None


async def _poll_loop():
    while True:
        states = get_latest()
        if states is not None:
            try:
                preds = compute_predictions(states)
                _history.append({"time": states["time"], "predictions": preds})
            except Exception as exc:
                print(f"[predictions_history_cache] poll failed: {exc}", flush=True)
        await asyncio.sleep(POLL_INTERVAL_S)


def start_background_poll():
    asyncio.create_task(_poll_loop())
