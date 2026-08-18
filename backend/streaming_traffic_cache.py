"""Background poller for streaming_traffic.compute_rolling_traffic(). Runs on its own
slower interval (this Beam pipeline takes several seconds to tens of seconds
depending on how much live history has accumulated -- far too slow to run inline
during a /predictions request, which needs to stay fast). predictions_service.py reads
the cached result instead of calling the Beam pipeline directly.
"""

import asyncio
from typing import Optional

from backend.live_state_cache import get_history
from backend.streaming_traffic import compute_rolling_traffic

POLL_INTERVAL_S = 90

_latest: Optional[dict[str, dict[str, int]]] = None


def get_latest_traffic() -> Optional[dict[str, dict[str, int]]]:
    return _latest


async def _poll_loop():
    global _latest
    while True:
        history = get_history()
        if history:
            try:
                _latest = await asyncio.to_thread(compute_rolling_traffic, history)
            except Exception as exc:
                print(f"[streaming_traffic_cache] poll failed: {exc}", flush=True)
        await asyncio.sleep(POLL_INTERVAL_S)


def start_background_poll():
    asyncio.create_task(_poll_loop())
