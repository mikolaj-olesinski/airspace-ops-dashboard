"""Loads scripts/fetch_aircraft_db.py's output once, lazily, at first lookup: a static
icao24 -> {typecode, manufacturer, model, operator, registration} table. Not refreshed
live -- aircraft registrations change on the order of months/years, nothing here needs
to be current-to-the-second the way live positions or weather do.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

DB_PATH = "data/raw/aircraft_db.parquet"

_lookup: dict | None = None


def _load() -> dict:
    # scripts/fetch_aircraft_db.py already collapsed each of manufacturer/operator down
    # from several source columns (many are blank per-row in OpenSky's raw database) --
    # this just reads its output as-is.
    df = pd.read_parquet(DB_PATH)
    return {
        row["icao24"]: {
            "typecode": row["typecode"],
            "manufacturer": row["manufacturer"],
            "model": row["model"],
            "operator": row["operator"],
            "registration": row["registration"],
        }
        for row in df.to_dict("records")
    }


def lookup_aircraft(icao24: str) -> dict | None:
    """None if the database hasn't been fetched yet (run scripts/fetch_aircraft_db.py)
    or this tail number simply isn't in it -- both are treated the same by callers."""
    global _lookup
    if _lookup is None:
        try:
            _lookup = _load()
        except FileNotFoundError:
            _lookup = {}
    return _lookup.get(icao24.lower())
