"""Current (not historical) weather per airport, from the Open-Meteo forecast API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.http_utils import make_session, run_with_hard_timeout
from ml.features import AIRPORT_COORDS

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HARD_TIMEOUT_S = 15


def _fetch_current_weather(icao: str) -> dict:
    lat, lon = AIRPORT_COORDS[icao]
    resp = make_session().get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            # same variable names as the training features (ml/features.py), so no
            # renaming/mapping is needed on the way into the model
            "current": "temperature_2m,precipitation,wind_speed_10m",
        },
        timeout=(5, 10),  # (connect, read)
    )
    resp.raise_for_status()
    current = resp.json()["current"]
    return {
        "temperature_2m": current["temperature_2m"],
        "precipitation": current["precipitation"],
        "wind_speed_10m": current["wind_speed_10m"],
    }


def fetch_current_weather(icao: str) -> dict:
    """Enforces a real wall-clock timeout -- see http_utils.run_with_hard_timeout."""
    return run_with_hard_timeout(_fetch_current_weather, icao, timeout=HARD_TIMEOUT_S)
