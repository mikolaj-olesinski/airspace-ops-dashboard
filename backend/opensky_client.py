"""Thin wrapper around the OpenSky Network REST API (anonymous tier, no auth)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.http_utils import make_session, run_with_hard_timeout
from ml.features import AIRPORT_COORDS

HARD_TIMEOUT_S = 20

# OpenSky's anonymous tier is rate-limited; retrying aggressively after a throttle just
# means waiting longer to fail the same way, so this uses a smaller retry budget than
# the default (used for Open-Meteo, where failures seen so far were transient SSL
# handshake errors, not rate limiting). A fresh Session per call, not a shared one --
# see http_utils.make_session's docstring for why.
OPENSKY_RETRIES = 2

# bounding box covering all 7 airports with a margin (derived from AIRPORT_COORDS
# rather than hardcoded, so it can't silently drift out of sync -- CLAUDE.md's own
# example bbox {lamin: 49, ...} actually clips Munich, whose latitude is 48.35)
_MARGIN_DEG = 2.0
_lats = [lat for lat, lon in AIRPORT_COORDS.values()]
_lons = [lon for lat, lon in AIRPORT_COORDS.values()]
BBOX = {
    "lamin": min(_lats) - _MARGIN_DEG,
    "lomin": min(_lons) - _MARGIN_DEG,
    "lamax": max(_lats) + _MARGIN_DEG,
    "lomax": max(_lons) + _MARGIN_DEG,
}
STATES_URL = "https://opensky-network.org/api/states/all"

STATE_FIELDS = [
    "icao24",
    "callsign",
    "origin_country",
    "time_position",
    "last_contact",
    "longitude",
    "latitude",
    "baro_altitude",
    "on_ground",
    "velocity",
    "true_track",
    "vertical_rate",
    "sensors",
    "geo_altitude",
    "squawk",
    "spi",
    "position_source",
]


def _fetch_live_states() -> dict:
    resp = make_session(OPENSKY_RETRIES).get(STATES_URL, params=BBOX, timeout=(5, 15))
    resp.raise_for_status()
    payload = resp.json()

    aircraft = []
    for state in payload.get("states") or []:
        row = dict(zip(STATE_FIELDS, state))
        if row.get("callsign"):
            row["callsign"] = row["callsign"].strip()
        aircraft.append(row)

    return {"time": payload.get("time"), "aircraft": aircraft}


def fetch_live_states() -> dict:
    """Returns {"time": <unix ts>, "aircraft": [{...}, ...]} for the bounding box.
    Enforces a real wall-clock timeout -- see http_utils.run_with_hard_timeout."""
    return run_with_hard_timeout(_fetch_live_states, timeout=HARD_TIMEOUT_S)


def count_aircraft_near(aircraft: list, lat: float, lon: float, radius_deg: float = 0.5) -> int:
    """Rough live-congestion proxy: aircraft currently within `radius_deg` degrees
    (~55km at these latitudes) of an airport's coordinates. Not a true traffic-in-
    the-last-hour count (OpenSky's free tier doesn't expose per-airport departure
    history) -- see backend/model_service.py for how this is used and documented."""
    count = 0
    for a in aircraft:
        if a["latitude"] is None or a["longitude"] is None:
            continue
        if abs(a["latitude"] - lat) <= radius_deg and abs(a["longitude"] - lon) <= radius_deg:
            count += 1
    return count
