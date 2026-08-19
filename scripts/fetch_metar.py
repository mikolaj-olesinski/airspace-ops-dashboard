"""Historical METAR (aviation-specific weather: visibility, cloud ceiling, wind gusts)
per airport, 2023-2025, from Iowa State University's Mesonet ASOS archive
(https://mesonet.agron.iastate.edu/ASOS/ -- free, no key). This is a different, more
aviation-specific signal than Open-Meteo's generic forecast (fetch_weather.py): ceiling
and visibility are what actually drive ATC spacing and go/no-go decisions, so they're a
more direct proxy for weather-caused delay than temperature/precipitation alone.

Mirrors fetch_weather.py's shape (one script, one output parquet, read back by
ml/features.py / pipeline/beam_features.py) so it slots into the same pipeline.
"""

import sys
import time
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from ml.features import AIRPORTS, flight_category_code

START = {"year1": 2023, "month1": 1, "day1": 1}
END = {"year2": 2025, "month2": 12, "day2": 31}
OUT_PATH = "data/raw/metar_2023_2025.parquet"

BASE_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
FIELDS = ["vsby", "gust", "skyc1", "skyl1", "skyc2", "skyl2", "skyc3", "skyl3", "skyc4", "skyl4"]
CEILING_COVERS = {"BKN", "OVC", "VV"}


def fetch_one(station: str) -> pd.DataFrame:
    resp = requests.get(
        BASE_URL,
        params={
            "station": station,
            "data": ",".join(FIELDS),
            **START,
            **END,
            "tz": "Etc/UTC",
            "format": "onlycomma",
            "latlon": "no",
            "elev": "no",
            "missing": "M",
            "trace": "T",
            "direct": "no",
            "report_type": 3,  # routine + special reports, not every 1-min ob
        },
        timeout=120,
    )
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text), na_values=["M"])
    df["airport"] = station
    return df


def row_ceiling_ft(row: pd.Series) -> float:
    """Ceiling = the lowest layer reported as broken/overcast/vertical-visibility
    (FAA definition) -- a FEW or SCT layer doesn't count as a ceiling. Missing/no such
    layer reported at all -> treat as unlimited (well above any threshold that matters)."""
    bases = [
        row[f"skyl{i}"]
        for i in (1, 2, 3, 4)
        if row.get(f"skyc{i}") in CEILING_COVERS and pd.notna(row.get(f"skyl{i}"))
    ]
    return min(bases) if bases else 12_000.0


def main():
    frames = []
    for code in AIRPORTS:
        print(f"fetching METAR for {code}...", flush=True)
        frames.append(fetch_one(code))
        time.sleep(1)

    combined = pd.concat(frames, ignore_index=True)
    combined["ceiling_ft"] = combined.apply(row_ceiling_ft, axis=1)
    combined["valid"] = pd.to_datetime(combined["valid"])
    combined["hour"] = combined["valid"].dt.floor("h")

    # a handful of hours have more than one report (routine + special); collapse to one
    # row per (airport, hour) -- worst ceiling and average visibility in that hour, the
    # same "what would ATC have been dealing with" spirit as the live radius-count proxy
    hourly = combined.groupby(["airport", "hour"], as_index=False).agg(
        visibility_mi=("vsby", "mean"),
        ceiling_ft=("ceiling_ft", "min"),
    )
    hourly["flight_category"] = hourly.apply(
        lambda r: flight_category_code(r["visibility_mi"], r["ceiling_ft"]), axis=1
    )
    # stored as a string in the same "%Y-%m-%dTHH:00" shape as fetch_weather.py's
    # Open-Meteo output, so beam_features.py can join both the same way
    hourly["hour"] = hourly["hour"].dt.strftime("%Y-%m-%dT%H:00")

    hourly.to_parquet(OUT_PATH, index=False)
    print(f"saved {len(hourly):,} rows to {OUT_PATH}")
    print(hourly.groupby("airport").size())
    print("flight_category value counts:")
    print(hourly["flight_category"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
