"""FastAPI backend: proxies live aircraft state and serves per-airport delay-risk
predictions from the trained LightGBM model.

Endpoints (per CLAUDE.md's Phase 3 plan, plus /history for the frontend's time-slider):
  GET /live-states  -- latest cached aircraft positions from OpenSky (a background
                        poller in live_state_cache.py is the only thing that actually
                        calls OpenSky; this just reads the cache -- see that module's
                        docstring for why)
  GET /history       -- the last ~1h of polled snapshots, for the frontend's
                        time-slider/playback (no per-client accumulation needed)
  GET /predictions   -- delay-risk score per airport, computed from live traffic +
                        weather (see model_service.py for how "live" features are
                        approximated)

/briefing (the LangGraph ops-briefing agent) is Phase 4 and deliberately not stubbed
here yet -- it needs an LLM provider key, which is a separate setup step.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.live_state_cache import get_history, get_latest, start_background_poll
from backend.model_service import get_model, predict_risk
from backend.opensky_client import count_aircraft_near
from backend.weather_client import fetch_current_weather
from ml.features import AIRPORT_COORDS

app = FastAPI(title="Live Airspace Ops Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # single-user local demo; would be locked down for real deployment
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_up_model():
    # loading the model from MLflow takes ~15s (mostly MLflow's own overhead, not the
    # model itself) -- pay that cost once at server startup, not on the first request
    get_model()


@app.on_event("startup")
async def _start_poller():
    start_background_poll()


@app.get("/")
def root():
    return {"status": "ok", "endpoints": ["/live-states", "/history", "/predictions"]}


@app.get("/live-states")
def live_states():
    latest = get_latest()
    if latest is None:
        raise HTTPException(status_code=503, detail="No live data yet -- still fetching the first snapshot")
    return latest


@app.get("/history")
def history():
    return {"snapshots": get_history()}


@app.get("/predictions")
def predictions():
    states = get_latest()
    if states is None:
        raise HTTPException(status_code=503, detail="No live data yet -- still fetching the first snapshot")

    airports = list(AIRPORT_COORDS)
    # the 7 weather calls are independent and network-bound -- fire them concurrently
    # instead of one after another (sequential was taking ~45s, too slow to poll every
    # 10-15s from the frontend)
    with ThreadPoolExecutor(max_workers=len(airports)) as pool:
        try:
            weather_by_airport = dict(zip(airports, pool.map(fetch_current_weather, airports)))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Weather request failed: {exc}") from exc

    results = []
    for airport, (lat, lon) in AIRPORT_COORDS.items():
        live_traffic_count = count_aircraft_near(states["aircraft"], lat, lon)
        results.append(predict_risk(airport, live_traffic_count, weather_by_airport[airport]))

    return {"computed_at": states["time"], "predictions": results}
