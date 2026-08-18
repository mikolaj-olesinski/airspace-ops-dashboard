"""Prototype run of the feature engineering logic in ml/features.py, on the full
filtered Eurocontrol dataset. Goal: validate the feature logic (and check it holds
up at full scale) before porting it to an Apache Beam pipeline.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.features import FEATURE_COLUMNS, TARGET_COLUMN, build_features, load_flights, load_weather

FLIGHTS_PATH = "data/raw/eurocontrol_filtered"
WEATHER_PATH = "data/raw/weather_2023_2025.parquet"
OUT_PATH = "data/processed/features_prototype.parquet"


def main():
    t0 = time.time()
    print("loading flights...", flush=True)
    flights = load_flights(FLIGHTS_PATH)
    print(f"  {len(flights):,} rows in {time.time() - t0:.0f}s", flush=True)

    print("loading weather...", flush=True)
    weather = load_weather(WEATHER_PATH)
    print(f"  {len(weather):,} rows", flush=True)

    print("building features...", flush=True)
    t1 = time.time()
    features = build_features(flights, weather)
    print(f"  done in {time.time() - t1:.0f}s, shape={features.shape}", flush=True)

    print("\n--- missing values ---")
    print(features[FEATURE_COLUMNS + [TARGET_COLUMN]].isna().sum())

    print("\n--- weather join coverage ---")
    print(f"rows with weather data: {features['temperature_2m'].notna().mean():.1%}")

    print("\n--- numeric feature stats ---")
    numeric_cols = ["hour_of_day", "day_of_week", "temperature_2m", "precipitation",
                     "wind_speed_10m", "traffic_1h", "traffic_3h", "delay_rate_1h", "delay_rate_3h"]
    print(features[numeric_cols].describe().T)

    print("\n--- correlation with target (delayed_15min) ---")
    corr = features[numeric_cols + [TARGET_COLUMN]].corr()[TARGET_COLUMN].drop(TARGET_COLUMN)
    print(corr.sort_values(key=abs, ascending=False))

    print("\n--- delay rate by airport ---")
    print(features.groupby("adep")[TARGET_COLUMN].agg(["mean", "count"]).sort_values("mean", ascending=False))

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    features[["first_seen"] + FEATURE_COLUMNS + [TARGET_COLUMN]].to_parquet(OUT_PATH)
    print(f"\nsaved to {OUT_PATH} ({time.time() - t0:.0f}s total)", flush=True)


if __name__ == "__main__":
    main()
