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

from ml.features import AIRPORTS, FEATURE_COLUMNS

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


def risk_level(score: float) -> str:
    if score < RISK_THRESHOLDS["low"]:
        return "low"
    if score < RISK_THRESHOLDS["medium"]:
        return "medium"
    return "high"


def build_feature_row(airport: str, traffic_1h: int, traffic_3h: int, weather: dict) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    delay_rate = HISTORICAL_DELAY_RATE.get(airport, sum(HISTORICAL_DELAY_RATE.values()) / len(HISTORICAL_DELAY_RATE))

    row = {
        "adep": airport,
        "hour_of_day": now.hour,
        "day_of_week": now.weekday(),
        "month": now.month,
        "is_weekend": int(now.weekday() in (5, 6)),
        "temperature_2m": weather["temperature_2m"],
        "precipitation": weather["precipitation"],
        "wind_speed_10m": weather["wind_speed_10m"],
        "traffic_1h": traffic_1h,
        "traffic_3h": traffic_3h,
        "delay_rate_1h": delay_rate,
        "delay_rate_3h": delay_rate,
        "typecode": None,
    }
    df = pd.DataFrame([row])
    df["adep"] = df["adep"].astype("category")
    df["typecode"] = df["typecode"].astype("category")
    return df[FEATURE_COLUMNS]


def predict_risk(
    airport: str,
    live_traffic_count: int,
    weather: dict,
    traffic_1h: int | None = None,
    traffic_3h: int | None = None,
) -> dict:
    """live_traffic_count is the instantaneous "aircraft within radius right now"
    figure, always shown in the response for the UI. traffic_1h/traffic_3h, when
    available from streaming_traffic_cache.py's Beam computation, are what actually
    feed the model instead -- see this module's docstring."""
    model = get_model()
    X = build_feature_row(
        airport,
        traffic_1h if traffic_1h is not None else live_traffic_count,
        traffic_3h if traffic_3h is not None else live_traffic_count,
        weather,
    )
    score = float(model.predict(X)[0])
    return {
        "airport": airport,
        "risk_score": round(score, 4),
        "risk_level": risk_level(score),
        "live_traffic_count": live_traffic_count,
        "weather": weather,
    }
