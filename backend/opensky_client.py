"""Thin wrapper around the OpenSky Network REST API.

Uses a registered OAuth2 client (OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET in
backend/.env) when present -- a separate, larger quota than the anonymous tier, and
what actually got this project unblocked after burning through the anonymous daily
budget during development. Falls back to anonymous (no auth header) if the client
credentials aren't set, so this still works for local dev without them.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.http_utils import make_session, run_with_hard_timeout
from ml.features import AIRPORT_COORDS

load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
)

_token: str | None = None
_token_expires_at: float = 0.0

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


def _get_access_token() -> str | None:
    """OAuth2 client-credentials flow. Tokens last ~30min; refreshed a minute early
    so an in-flight request never gets a token that expires mid-call."""
    global _token, _token_expires_at
    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    if _token is not None and time.time() < _token_expires_at - 60:
        return _token

    resp = make_session(OPENSKY_RETRIES).post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=(5, 15),
    )
    resp.raise_for_status()
    body = resp.json()
    _token = body["access_token"]
    _token_expires_at = time.time() + body.get("expires_in", 1800)
    return _token


def _fetch_live_states() -> dict:
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = make_session(OPENSKY_RETRIES).get(STATES_URL, params=BBOX, headers=headers, timeout=(5, 15))
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
