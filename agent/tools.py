"""Tools the Q&A agent (agent/qa_agent.py) can call to look up live data before
answering. Each tool reads from the same caches the REST API serves from
(backend/live_state_cache.py, backend/predictions_history_cache.py) -- the agent never
calls OpenSky/Open-Meteo/the model directly, it only reads what's already live.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.tools import tool

from backend.live_state_cache import get_latest
from backend.predictions_history_cache import get_predictions_history
from backend.predictions_service import compute_predictions


@tool
def get_current_predictions() -> str:
    """Get the current delay-risk prediction for every tracked airport (EDDF, EPWA,
    EGLL, LFPG, EHAM, EDDM, EPGD): risk score, risk level, live traffic count, and
    current weather. Use this for questions about which airport is riskiest, or about
    a specific airport's current conditions."""
    states = get_latest()
    if states is None:
        return "No live data available yet."
    preds = compute_predictions(states)
    lines = []
    for p in sorted(preds, key=lambda p: p["risk_score"], reverse=True):
        w = p["weather"]
        lines.append(
            f"{p['airport']}: risk {round(p['risk_score'] * 100)}% ({p['risk_level']}), "
            f"{p['live_traffic_count']} aircraft nearby, wind {w['wind_speed_10m']} km/h, "
            f"temp {w['temperature_2m']}C, precip {w['precipitation']} mm"
        )
    return "\n".join(lines)


@tool
def find_aircraft(query: str) -> str:
    """Look up live aircraft by callsign or ICAO24 hex address (case-insensitive,
    partial match is fine, e.g. "DLH" matches all Lufthansa callsigns starting with
    DLH). Returns position, altitude, speed, heading and origin country for up to 5
    matches. Use this when the user asks about a specific flight or aircraft."""
    states = get_latest()
    if states is None:
        return "No live data available yet."
    q = query.strip().upper()
    matches = [
        a
        for a in states["aircraft"]
        if (a.get("callsign") or "").upper().find(q) != -1 or a.get("icao24", "").upper().find(q) != -1
    ][:5]
    if not matches:
        return f"No aircraft found matching '{query}' in the current live snapshot."
    lines = []
    for a in matches:
        lines.append(
            f"{(a.get('callsign') or '(no callsign)').strip()} (icao24={a['icao24']}): "
            f"origin {a.get('origin_country')}, "
            f"altitude {round(a['baro_altitude']) if a.get('baro_altitude') is not None else 'n/a'} m, "
            f"speed {round(a['velocity'] * 3.6) if a.get('velocity') is not None else 'n/a'} km/h, "
            f"heading {round(a['true_track']) if a.get('true_track') is not None else 'n/a'}°, "
            f"position ({a.get('latitude')}, {a.get('longitude')})"
        )
    return "\n".join(lines)


@tool
def get_airport_risk_trend(airport: str) -> str:
    """Get the recent delay-risk trend for one airport (ICAO code, e.g. "EDDM") over
    roughly the last hour, as a sequence of risk-score percentages over time. Use this
    when the user asks whether an airport's risk is going up, down, or has been stable."""
    history = get_predictions_history()
    code = airport.strip().upper()
    series = []
    for snap in history:
        p = next((p for p in snap["predictions"] if p["airport"] == code), None)
        if p is not None:
            series.append(round(p["risk_score"] * 100))
    if not series:
        return f"No trend data yet for {code} (or unknown airport code)."
    return f"{code} risk trend (oldest to newest, %): {', '.join(map(str, series))}"


TOOLS = [get_current_predictions, find_aircraft, get_airport_risk_trend]
