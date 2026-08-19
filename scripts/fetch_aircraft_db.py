"""Static icao24 -> aircraft type/manufacturer/operator lookup, from OpenSky's public
aircraft metadata database (a static file dump, not an API -- no key, no rate limit).

Used to turn a live-tracked aircraft into something the delay-risk model can actually
use per-flight: the model was trained with a real `typecode` per flight, but live
/predictions always sends typecode=None since an airport-level prediction isn't about
one specific aircraft. Looking a clicked aircraft's tail number up here lets
backend/aircraft_risk_service.py's compute_aircraft_risk() feed its real type in instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

URL = "https://opensky-network.org/datasets/metadata/aircraftDatabase.csv"
OUT_PATH = "data/raw/aircraft_db.parquet"
# `manufacturername` and `operator` are each blank for a large share of rows -- the
# readable value often only exists in a sibling column (manufacturericao for smaller/
# private aircraft, owner/operatorcallsign/operatoricao for operator), so all of them
# get kept and collapsed with a fallback chain below rather than trusting one column.
KEEP_COLUMNS = [
    "icao24",
    "registration",
    "manufacturericao",
    "manufacturername",
    "model",
    "typecode",
    "operator",
    "operatorcallsign",
    "operatoricao",
    "owner",
]


def _first_nonempty(*values: str) -> "str | None":
    for v in values:
        if v:
            return v
    return None


def main():
    print("downloading OpenSky aircraft database (~90MB, one-time)...", flush=True)
    df = pd.read_csv(URL, usecols=KEEP_COLUMNS, dtype=str, keep_default_na=False, low_memory=False)
    df = df[df["icao24"] != ""].copy()
    df["icao24"] = df["icao24"].str.lower()
    df = df.drop_duplicates(subset="icao24", keep="first")

    out = pd.DataFrame(
        {
            "icao24": df["icao24"],
            "registration": df["registration"],
            "manufacturer": [
                _first_nonempty(a, b) for a, b in zip(df["manufacturername"], df["manufacturericao"])
            ],
            "model": df["model"],
            "typecode": df["typecode"],
            "operator": [
                _first_nonempty(a, b, c, d)
                for a, b, c, d in zip(df["operator"], df["owner"], df["operatorcallsign"], df["operatoricao"])
            ],
        }
    )
    out = out.replace("", None)
    out.to_parquet(OUT_PATH, index=False)
    print(f"saved {len(out):,} aircraft to {OUT_PATH}")
    print(f"rows with a usable typecode: {out['typecode'].notna().sum():,}")
    print(f"rows with a usable manufacturer: {out['manufacturer'].notna().sum():,}")
    print(f"rows with a usable operator: {out['operator'].notna().sum():,}")


if __name__ == "__main__":
    main()
