"""FastAPI backend: proxies live aircraft state, serves per-airport delay-risk
predictions from the trained LightGBM model, and a LangGraph-generated ops briefing.

Endpoints (per CLAUDE.md's Phase 3/4 plan, plus a couple of history endpoints the
frontend uses for its time-slider and risk-trend sparklines):
  GET /live-states          -- latest cached aircraft positions from OpenSky (a
                                background poller in live_state_cache.py is the only
                                thing that actually calls OpenSky; this just reads the
                                cache -- see that module's docstring for why)
  GET /history               -- the last ~1h of polled aircraft snapshots, for the
                                frontend's time-slider/playback
  GET /predictions           -- delay-risk score per airport, computed from live
                                traffic + weather (see model_service.py for how "live"
                                features are approximated)
  GET /predictions/history   -- the last ~1h of polled predictions, for the risk-trend
                                sparklines shown when an airport is selected
                                (predictions_history_cache.py)
  GET /briefing               -- 2-3 sentence ops briefing from the LangGraph agent
                                (agent/briefing_agent.py), generated from the same
                                predictions as /predictions and cached for ~60s
                                (briefing_cache.py) so polling doesn't hammer the LLM
  GET /agent/ask               -- free-text Q&A against a LangGraph ReAct agent
                                (agent/qa_agent.py) with tools for live predictions,
                                aircraft lookup, and risk trends (agent/tools.py)
  GET /aircraft/{icao24}/risk  -- delay-risk prediction for ONE specific tracked
                                aircraft, using its real aircraft type instead of the
                                airport-level typecode=None (aircraft_risk_service.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.qa_agent import ask as agent_ask
from backend.aircraft_risk_service import AircraftRiskUnavailable, compute_aircraft_risk
from backend.briefing_cache import get_airport_briefing, get_briefing
from backend.live_state_cache import get_history, get_latest
from backend.live_state_cache import start_background_poll as start_states_poll
from backend.model_service import get_feature_importance, get_model
from backend.predictions_history_cache import get_predictions_history
from backend.predictions_history_cache import start_background_poll as start_predictions_poll
from backend.predictions_service import compute_predictions
from backend.streaming_traffic_cache import start_background_poll as start_traffic_poll

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
async def _start_pollers():
    start_states_poll()
    start_predictions_poll()
    start_traffic_poll()


@app.get("/")
def root():
    return {
        "status": "ok",
        "endpoints": [
            "/live-states",
            "/history",
            "/predictions",
            "/predictions/history",
            "/briefing",
            "/briefing/airport",
            "/agent/ask",
            "/model/feature-importance",
            "/aircraft/{icao24}/risk",
        ],
    }


@app.get("/live-states")
def live_states():
    latest = get_latest()
    if latest is None:
        raise HTTPException(status_code=503, detail="No live data yet -- still fetching the first snapshot")
    return latest


@app.get("/history")
def history():
    return {"snapshots": get_history()}


def _predictions_for_latest() -> tuple[dict, list[dict]]:
    states = get_latest()
    if states is None:
        raise HTTPException(status_code=503, detail="No live data yet -- still fetching the first snapshot")
    try:
        return states, compute_predictions(states)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weather request failed: {exc}") from exc


@app.get("/predictions")
def predictions():
    states, results = _predictions_for_latest()
    return {"computed_at": states["time"], "predictions": results}


@app.get("/predictions/history")
def predictions_history():
    return {"snapshots": get_predictions_history()}


@app.get("/briefing")
def briefing():
    _states, results = _predictions_for_latest()
    try:
        return get_briefing(results)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Briefing generation failed: {exc}") from exc


@app.get("/briefing/airport")
def airport_briefing(code: str):
    _states, results = _predictions_for_latest()
    code = code.strip().upper()
    prediction = next((p for p in results if p["airport"] == code), None)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Unknown airport code: {code}")
    trend = [
        round(p["risk_score"] * 100)
        for snap in get_predictions_history()
        for p in snap["predictions"]
        if p["airport"] == code
    ]
    try:
        return get_airport_briefing(prediction, trend)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Airport briefing generation failed: {exc}") from exc


@app.get("/aircraft/{icao24}/risk")
def aircraft_risk(icao24: str):
    states = get_latest()
    if states is None:
        raise HTTPException(status_code=503, detail="No live data yet -- still fetching the first snapshot")
    icao24 = icao24.strip().lower()
    aircraft = next((a for a in states["aircraft"] if a["icao24"] == icao24), None)
    if aircraft is None:
        raise HTTPException(status_code=404, detail=f"Aircraft {icao24} isn't in the current live snapshot")
    try:
        return compute_aircraft_risk(aircraft)
    except AircraftRiskUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Aircraft risk computation failed: {exc}") from exc


@app.get("/agent/ask")
def agent_ask_endpoint(q: str, thread_id: str = "default"):
    try:
        return {"question": q, "answer": agent_ask(q, thread_id=thread_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent failed: {exc}") from exc


@app.get("/model/feature-importance")
def feature_importance():
    return {"features": get_feature_importance()}
