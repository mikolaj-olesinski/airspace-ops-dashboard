"""Computes per-airport delay-risk predictions from a live-states snapshot. Shared by
the /predictions and /briefing endpoints (main.py) and by predictions_history_cache.py's
background poller, so all three stay consistent with each other."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.model_service import predict_risk
from backend.opensky_client import count_aircraft_near
from backend.weather_client import fetch_current_weather
from ml.features import AIRPORT_COORDS


def compute_predictions(states: dict) -> list[dict]:
    airports = list(AIRPORT_COORDS)
    # the 7 weather calls are independent and network-bound -- fire them concurrently
    # instead of one after another (sequential was taking ~45s, too slow to poll every
    # 10-15s from the frontend)
    with ThreadPoolExecutor(max_workers=len(airports)) as pool:
        weather_by_airport = dict(zip(airports, pool.map(fetch_current_weather, airports)))

    results = []
    for airport, (lat, lon) in AIRPORT_COORDS.items():
        live_traffic_count = count_aircraft_near(states["aircraft"], lat, lon)
        results.append(predict_risk(airport, live_traffic_count, weather_by_airport[airport]))
    return results
