"""Background poller that owns all OpenSky access: a single fixed-interval loop
populates an in-memory cache (latest snapshot) and a rolling history buffer, shared
across every request and every connected client.

Two reasons this beats each request calling OpenSky directly (which is what
/live-states and /predictions did before):
  - OpenSky's anonymous tier has a small daily credit budget. N open browser tabs each
    triggering their own call on every poll would multiply usage by N; this bounds
    usage to one call per POLL_INTERVAL_S no matter how many clients are connected.
  - It gives the frontend's time-slider real history (the last HISTORY_MAXLEN
    snapshots, ~1h) instead of only whatever it happened to accumulate client-side
    since the page was opened.
"""

import asyncio
from collections import deque
from typing import Optional

from backend.opensky_client import fetch_live_states

POLL_INTERVAL_S = 12
HISTORY_MAXLEN = 300  # ~1h of history at one snapshot per POLL_INTERVAL_S

_latest: Optional[dict] = None
_history: deque = deque(maxlen=HISTORY_MAXLEN)


def get_latest() -> Optional[dict]:
    return _latest


def get_history() -> list:
    return list(_history)


async def _poll_loop():
    global _latest
    while True:
        try:
            states = await asyncio.to_thread(fetch_live_states)
            _latest = states
            _history.append(states)
        except Exception as exc:
            print(f"[live_state_cache] poll failed: {exc}", flush=True)
        await asyncio.sleep(POLL_INTERVAL_S)


def start_background_poll():
    asyncio.create_task(_poll_loop())
