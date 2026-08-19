"""Loads the latest trained model from MLflow and builds live per-airport risk scores.

Live feature construction is necessarily an approximation of the training features
(ml/features.py), since OpenSky's free tier gives a snapshot of aircraft positions, not
a per-airport departure/delay history:
  - traffic_1h / traffic_3h: at training time this was a true rolling count of recent
    departures. Live, backend/streaming_traffic.py computes a genuine rolling-window
    count via Beam (distinct aircraft seen near the airport in the trailing 1h/3h,
    reprocessing the buffered snapshot history -- see that module's docstring) --
    closer to the training semantics than a single instant, but still "aircraft seen
    nearby" rather than "aircraft that departed", since OpenSky's free tier has no
    departure events to count. Until that background computation has produced its
    first result (a few minutes after startup), predict_risk() falls back to the
    single-snapshot proxy (aircraft within ~2 degrees right now) for both windows.
  - delay_rate_1h / delay_rate_3h: at training time this was the rolling recent delay
    rate at that airport. Live, there's no free real-time source for "how many of the
    last N flights were delayed", so this falls back to each airport's historical
    average delay rate (HISTORICAL_DELAY_RATE below, computed once from the training
    set). This means the model effectively can't see today's actual delay momentum --
    a known, documented limitation of the demo, not a hidden one.
  - typecode: a live prediction isn't about one specific flight, so this is left
    missing (None) -- LightGBM handles missing categoricals natively.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

import mlflow
import pandas as pd

from ml.features import AIRPORTS, FEATURE_COLUMNS, FLIGHT_CATEGORIES
from ml.features import is_holiday as compute_is_holiday

MLFLOW_TRACKING_URI = "file:./mlruns"
MLFLOW_EXPERIMENT = "airspace-delay-risk"

# mean delayed_15min per airport over the full training set (data/processed/features-*
# .parquet) -- see ml/train.py's per-airport breakdown / README for how this was
# produced. Used as the live fallback for delay_rate_1h/3h (see module docstring).
HISTORICAL_DELAY_RATE = {
    "EDDF": 0.0499,
    "EDDM": 0.0600,
    "EGLL": 0.0359,
    "EHAM": 0.0407,
    "EPGD": 0.0521,
    "EPWA": 0.0500,
    "LFPG": 0.0383,
}

RISK_THRESHOLDS = {"low": 0.25, "medium": 0.40}  # >= medium threshold => "high"

# human-readable labels for FEATURE_COLUMNS, used when explaining a prediction (see
# _top_factors below) -- shown to users, so plain language rather than the raw column name
_FEATURE_LABEL = {
    "traffic_1h": "traffic in the last hour",
    "traffic_3h": "traffic in the last 3 hours",
    "wind_speed_10m": "wind speed",
    "precipitation": "precipitation",
    "temperature_2m": "temperature",
    "hour_of_day": "time of day",
    "day_of_week": "day of week",
    "month": "time of year",
    "is_weekend": "weekend/weekday",
    "is_holiday": "public holiday",
    "visibility_mi": "visibility",
    "ceiling_ft": "cloud ceiling",
    "flight_category": "flight category",
    "delay_rate_1h": "recent delay rate",
    "delay_rate_3h": "recent delay rate",
    "adep": "airport baseline",
    "typecode": "aircraft type",
}

_model = None


def _load_latest_final_model():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    runs = mlflow.search_runs(
        experiment_names=[MLFLOW_EXPERIMENT],
        filter_string="tags.mlflow.runName = 'final_model'",
        order_by=["start_time DESC"],
        max_results=1,
    )
    if runs.empty:
        raise RuntimeError(
            f"No 'final_model' run found in MLflow experiment '{MLFLOW_EXPERIMENT}'. "
            "Run `python ml/train.py` first."
        )
    run_id = runs.iloc[0]["run_id"]
    return mlflow.lightgbm.load_model(f"runs:/{run_id}/model")


def get_model():
    global _model
    if _model is None:
        _model = _load_latest_final_model()
    return _model


def get_feature_importance() -> list[dict]:
    model = get_model()
    names = model.feature_name()
    gains = model.feature_importance(importance_type="gain")
    total = float(sum(gains)) or 1.0
    ranked = sorted(zip(names, gains), key=lambda kv: kv[1], reverse=True)
    return [{"feature": name, "importance": round(float(g) / total, 4)} for name, g in ranked]


def _stringify(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


_MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _format_value(feature: str, v) -> str:
    """Turns a raw feature value into something a human (or the LLM writing about it)
    reads naturally -- "23:00" instead of "23", "68%" instead of "0.68" -- without
    changing what actually feeds the model."""
    s = _stringify(v)
    if s == "n/a":
        return s
    try:
        if feature == "hour_of_day":
            return f"{int(float(s)):02d}:00"
        if feature == "day_of_week":
            return _DAY_NAMES[int(float(s))]
        if feature == "month":
            return _MONTH_NAMES[int(float(s))]
        if feature in ("delay_rate_1h", "delay_rate_3h"):
            return f"{round(float(s) * 100)}%"
        if feature == "flight_category":
            return FLIGHT_CATEGORIES[int(float(s))]
    except (ValueError, IndexError):
        return s
    if feature == "wind_speed_10m":
        return f"{s} km/h"
    if feature == "temperature_2m":
        return f"{s}°C"
    if feature == "precipitation":
        return f"{s} mm"
    if feature in ("traffic_1h", "traffic_3h"):
        return f"{s} aircraft"
    if feature == "is_holiday":
        return "yes" if s == "1" else "no"
    if feature == "visibility_mi":
        return f"{s} mi"
    if feature == "ceiling_ft":
        return "unlimited" if float(s) >= 12_000 else f"{s} ft"
    return s


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value))


def _top_factors(model, X: pd.DataFrame, top_n: int = 3) -> list[dict]:
    """The model's own reasoning for ONE prediction -- LightGBM's native per-row SHAP
    contributions (pred_contrib=True), not a guess. Positive contribution means that
    feature's actual value pushed this prediction's risk up from the model's average;
    negative means it pushed it down. This is what grounds the "why is the risk what it
    is" briefings/chat answers in real numbers instead of the LLM inventing a plausible-
    sounding cause.

    typecode is excluded whenever it's actually missing for this row (the normal
    airport-level case, see build_feature_row's docstring) -- its contribution there is
    just the training-time "missing" bucket's average effect, not a real live signal, so
    surfacing it as a top driver would claim "aircraft type" explains the risk while
    never naming one. When a real typecode IS supplied (a specific aircraft's
    aircraft_risk_service.compute_aircraft_risk call), it's a genuine live value and stays
    in like any other feature."""
    contrib = model.predict(X, pred_contrib=True)[0]  # len == n_features + 1 (last = bias term)
    names = model.feature_name()
    ranked = sorted(
        (kv for kv in zip(names, contrib[:-1]) if not (kv[0] == "typecode" and _is_missing(X["typecode"].iloc[0]))),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )
    return [
        {
            "feature": name,
            "label": _FEATURE_LABEL.get(name, name),
            "value": _format_value(name, X[name].iloc[0]),
            "contribution": round(float(val), 4),
            "direction": "increases" if val > 0 else "decreases",
        }
        for name, val in ranked[:top_n]
        if abs(val) > 1e-6
    ]


def risk_level(score: float) -> str:
    if score < RISK_THRESHOLDS["low"]:
        return "low"
    if score < RISK_THRESHOLDS["medium"]:
        return "medium"
    return "high"


def build_feature_row(
    airport: str, traffic_1h: int, traffic_3h: int, weather: dict, metar: dict, typecode: str | None = None
) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    delay_rate = HISTORICAL_DELAY_RATE.get(airport, sum(HISTORICAL_DELAY_RATE.values()) / len(HISTORICAL_DELAY_RATE))

    row = {
        "adep": airport,
        "hour_of_day": now.hour,
        "day_of_week": now.weekday(),
        "month": now.month,
        "is_weekend": int(now.weekday() in (5, 6)),
        "is_holiday": compute_is_holiday(airport, now),
        "temperature_2m": weather["temperature_2m"],
        "precipitation": weather["precipitation"],
        "wind_speed_10m": weather["wind_speed_10m"],
        "visibility_mi": metar.get("visibility_mi"),
        "ceiling_ft": metar.get("ceiling_ft"),
        "flight_category": metar.get("flight_category"),
        "traffic_1h": traffic_1h,
        "traffic_3h": traffic_3h,
        "delay_rate_1h": delay_rate,
        "delay_rate_3h": delay_rate,
        # None for the ordinary airport-level prediction (not about one specific
        # flight); a real value when aircraft_risk_service.compute_aircraft_risk() has
        # looked one up for a clicked aircraft (backend/aircraft_db.py)
        "typecode": typecode,
    }
    df = pd.DataFrame([row])
    df["adep"] = df["adep"].astype("category")
    df["typecode"] = df["typecode"].astype("category")
    # weather/metar fields are None whenever that live source failed or didn't cover
    # this airport this poll (see predictions_service.py) -- a single-row DataFrame
    # with a None value infers dtype "object", which LightGBM's predict() rejects
    # outright ("pandas dtypes must be int, float or bool"), unlike a real NaN in a
    # float64 column, which it handles natively as a missing value. Cast explicitly so
    # a live source outage degrades the prediction instead of crashing it.
    numeric_cols = [
        "temperature_2m",
        "precipitation",
        "wind_speed_10m",
        "visibility_mi",
        "ceiling_ft",
        "flight_category",
    ]
    df[numeric_cols] = df[numeric_cols].astype(float)
    return df[FEATURE_COLUMNS]


def predict_risk(
    airport: str,
    live_traffic_count: int,
    weather: dict,
    metar: dict | None = None,
    traffic_1h: int | None = None,
    traffic_3h: int | None = None,
    typecode: str | None = None,
) -> dict:
    """live_traffic_count is the instantaneous "aircraft within radius right now"
    figure, always shown in the response for the UI. traffic_1h/traffic_3h, when
    available from streaming_traffic_cache.py's Beam computation, are what actually
    feed the model instead -- see this module's docstring. metar is missing (None) if
    aviationweather.gov's API failed or didn't cover this airport in that poll -- the
    model handles missing visibility/ceiling/flight_category the same as any other
    missing value, natively. typecode is only set for a specific-aircraft prediction
    (aircraft_risk_service.compute_aircraft_risk) -- ordinary airport-level predictions
    leave it None."""
    model = get_model()
    X = build_feature_row(
        airport,
        traffic_1h if traffic_1h is not None else live_traffic_count,
        traffic_3h if traffic_3h is not None else live_traffic_count,
        weather,
        metar or {},
        typecode,
    )
    score = float(model.predict(X)[0])
    return {
        "airport": airport,
        "risk_score": round(score, 4),
        "risk_level": risk_level(score),
        "live_traffic_count": live_traffic_count,
        "weather": weather,
        "metar": metar,
        "top_factors": _top_factors(model, X),
    }
