"""Per-aircraft delay-risk: given one specific tracked aircraft, look up its real
aircraft type (aircraft_db.py) and predict against the nearest tracked airport's
already-computed live context (predictions_history_cache.py) -- unlike the ordinary
airport-level prediction, which always sends typecode=None because it isn't about one
specific flight (see model_service.py's docstring). A separate module from
predictions_service.py specifically to avoid a circular import: predictions_history_
cache.py already imports predictions_service.compute_predictions, so this can't live
there and also import predictions_history_cache back.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.aircraft_db import lookup_aircraft
from backend.model_service import predict_risk
from backend.predictions_history_cache import get_latest_predictions
from ml.features import AIRPORT_COORDS


def _nearest_airport(lat: float, lon: float) -> str:
    return min(
        AIRPORT_COORDS,
        key=lambda code: (AIRPORT_COORDS[code][0] - lat) ** 2 + (AIRPORT_COORDS[code][1] - lon) ** 2,
    )


class AircraftRiskUnavailable(ValueError):
    """One specific, user-facing reason a per-aircraft prediction couldn't be computed
    -- main.py maps this to a 404 with the real reason in the body, instead of every
    cause collapsing into one generic, undiagnosable message."""


def compute_aircraft_risk(aircraft: dict) -> dict:
    """Raises AircraftRiskUnavailable if this aircraft has no usable type on file, or
    the airport-level prediction context isn't ready yet -- main.py turns that into a
    404 with the specific reason. Reuses the nearest tracked airport's already-fetched
    live weather/METAR/traffic (from the 30s predictions poller) instead of re-fetching
    live sources for a single click."""
    if aircraft.get("latitude") is None or aircraft.get("longitude") is None:
        raise AircraftRiskUnavailable(f"{aircraft.get('icao24')} has no live position this poll")

    info = lookup_aircraft(aircraft["icao24"])
    if info is None:
        raise AircraftRiskUnavailable(f"{aircraft['icao24']} isn't in the aircraft database")
    if not info.get("typecode"):
        raise AircraftRiskUnavailable(f"{aircraft['icao24']} has no aircraft type on file")

    nearest = _nearest_airport(aircraft["latitude"], aircraft["longitude"])
    latest_preds = get_latest_predictions()
    if not latest_preds:
        raise AircraftRiskUnavailable("no predictions computed yet -- still warming up")
    airport_pred = next((p for p in latest_preds if p["airport"] == nearest), None)
    if airport_pred is None:
        raise AircraftRiskUnavailable(f"no live prediction context for {nearest} yet")

    result = predict_risk(
        nearest,
        airport_pred["live_traffic_count"],
        airport_pred["weather"],
        metar=airport_pred["metar"],
        typecode=info["typecode"],
    )
    result["icao24"] = aircraft["icao24"]
    result["nearest_airport"] = nearest
    result["aircraft_info"] = info
    return result
