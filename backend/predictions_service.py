"""Computes per-airport delay-risk predictions from a live-states snapshot. Shared by
the /predictions and /briefing endpoints (main.py) and by predictions_history_cache.py's
background poller, so all three stay consistent with each other."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.metar_client import fetch_all_metar
from backend.model_service import predict_risk
from backend.opensky_client import count_aircraft_near
from backend.streaming_traffic_cache import get_latest_traffic
from backend.weather_client import fetch_current_weather
from ml.features import AIRPORT_COORDS


def _coalesce(*values):
    for v in values:
        if v is not None:
            return v
    return None


def compute_predictions(states: dict) -> list[dict]:
    airports = list(AIRPORT_COORDS)
    # the 7 Open-Meteo calls are independent and network-bound -- fire them
    # concurrently instead of one after another (sequential was taking ~45s, too slow
    # to poll every 10-15s from the frontend). METAR is a single batched call for all
    # 7 airports (see metar_client.py), so it just runs alongside them, not per-airport.
    # Neither source failing is fatal anymore (see below) -- Open-Meteo's free tier
    # burned through its ~10k/day quota during this project's own testing and stayed
    # 429'd for hours, and predictions used to just 502 whenever that happened.
    with ThreadPoolExecutor(max_workers=len(airports) + 1) as pool:
        weather_futures = {airport: pool.submit(fetch_current_weather, airport) for airport in airports}
        metar_future = pool.submit(fetch_all_metar)

        weather_by_airport = {}
        for airport, f in weather_futures.items():
            try:
                weather_by_airport[airport] = f.result()
            except Exception:
                weather_by_airport[airport] = {"temperature_2m": None, "precipitation": None, "wind_speed_10m": None}
        try:
            metar_by_airport = metar_future.result()
        except Exception:
            metar_by_airport = {}

    # the Beam-computed rolling window (streaming_traffic_cache.py) takes a while to
    # produce its first result after startup -- predict_risk() falls back to the
    # instant radius count for both windows until then
    rolling_traffic = get_latest_traffic() or {}

    results = []
    for airport, (lat, lon) in AIRPORT_COORDS.items():
        live_traffic_count = count_aircraft_near(states["aircraft"], lat, lon)
        traffic = rolling_traffic.get(airport, {})
        metar = metar_by_airport.get(airport)
        om_weather = weather_by_airport[airport]

        # METAR is the primary source for temp/wind -- a real reading from the
        # airport's own station, not an interpolated model-grid estimate -- with
        # Open-Meteo only as a fallback if METAR's missing for this poll. Precipitation
        # has no clean METAR equivalent, so it's Open-Meteo only (see metar_client.py).
        weather = {
            "temperature_2m": _coalesce(metar and metar.get("temperature_2m"), om_weather.get("temperature_2m")),
            "wind_speed_10m": _coalesce(metar and metar.get("wind_speed_10m"), om_weather.get("wind_speed_10m")),
            "precipitation": om_weather.get("precipitation"),
        }

        results.append(
            predict_risk(
                airport,
                live_traffic_count,
                weather,
                metar=metar,
                traffic_1h=traffic.get("traffic_1h"),
                traffic_3h=traffic.get("traffic_3h"),
            )
        )
    return results
