import time

import pandas as pd
import requests

AIRPORTS = {
    "EDDF": (50.0379, 8.5622),
    "EPWA": (52.1657, 20.9671),
    "EGLL": (51.4700, -0.4543),
    "LFPG": (49.0097, 2.5479),
    "EHAM": (52.3086, 4.7639),
    "EDDM": (48.3538, 11.7861),
    "EPGD": (54.3776, 18.4662),
}

START_DATE = "2023-01-01"
END_DATE = "2025-12-31"
OUT_PATH = "data/raw/weather_2023_2025.parquet"


def fetch_one(code, lat, lon):
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "hourly": "temperature_2m,precipitation,wind_speed_10m",
            "timezone": "UTC",
        },
        timeout=60,
    )
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    df = pd.DataFrame(hourly)
    df["airport"] = code
    return df


def main():
    frames = []
    for code, (lat, lon) in AIRPORTS.items():
        print(f"fetching {code}...", flush=True)
        frames.append(fetch_one(code, lat, lon))
        time.sleep(1)

    combined = pd.concat(frames, ignore_index=True)
    combined.to_parquet(OUT_PATH, index=False)
    print(f"saved {len(combined):,} rows to {OUT_PATH}")
    print(combined.groupby("airport").size())


if __name__ == "__main__":
    main()
