"""Live METAR (aviation-specific weather) for all 7 airports, from aviationweather.gov's
free public API (no key). One batched call for all airports at once (the API accepts a
comma-separated ids list) -- unlike Open-Meteo, which needs one call per airport (see
weather_client.py), so this is inherently much lighter on the free tier, and in practice
has been far more reliable: Open-Meteo's free tier hit its ~10k/day quota during this
project's own testing and stayed 429'd for hours, while this endpoint never did.

Feeds visibility_mi/ceiling_ft/flight_category -- the same three features
scripts/fetch_metar.py derives for training from historical Iowa Mesonet ASOS data.
flight_category is computed here with the exact same ml.features.flight_category_code()
formula used for training, rather than trusting this API's own `fltCat` field, so live
serving can't silently drift from what the model was actually trained on.

Also surfaces temperature_2m/wind_speed_10m -- a real reading from the airport's own
station, arguably more authoritative than Open-Meteo's interpolated model-grid estimate
for the same variables -- so predictions_service.py uses METAR as the primary source for
those two and only falls back to Open-Meteo if METAR's missing. Precipitation has no
clean METAR equivalent (present-weather codes like "RA"/"-SN", not a mm amount), so that
one still comes from Open-Meteo alone.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.http_utils import make_session, run_with_hard_timeout
from ml.features import AIRPORTS, flight_category_code, flight_category_label

METAR_URL = "https://aviationweather.gov/api/data/metar"
HARD_TIMEOUT_S = 15
CEILING_COVERS = {"BKN", "OVC", "VV"}


def _parse_visibility(visib) -> "float | None":
    """aviationweather.gov reports visibility as a string like "10+", "3", or "1/2"
    (statute miles), not a plain number."""
    if visib is None:
        return None
    if isinstance(visib, (int, float)):
        return float(visib)
    s = str(visib).strip()
    if s.endswith("+"):
        s = s[:-1]
    if s.startswith("M"):  # "M1/4" == "less than 1/4"
        s = s[1:]
    if "/" in s:
        try:
            num, den = s.split("/")
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _ceiling_ft(clouds: list | None) -> float:
    bases = [c["base"] for c in (clouds or []) if c.get("cover") in CEILING_COVERS and c.get("base") is not None]
    return min(bases) if bases else 12_000.0  # no BKN/OVC/VV layer reported -> unlimited


def _fetch_all() -> dict:
    resp = make_session().get(METAR_URL, params={"ids": ",".join(AIRPORTS), "format": "json"}, timeout=(5, 10))
    resp.raise_for_status()
    by_airport = {}
    for ob in resp.json():
        icao = ob.get("icaoId")
        if icao not in AIRPORTS:
            continue
        visibility_mi = _parse_visibility(ob.get("visib"))
        ceiling_ft = _ceiling_ft(ob.get("clouds"))
        category = flight_category_code(visibility_mi, ceiling_ft)
        wspd_kt = ob.get("wspd")  # METAR reports wind speed in knots, not km/h
        by_airport[icao] = {
            "visibility_mi": visibility_mi,
            "ceiling_ft": ceiling_ft,
            "flight_category": category,
            # resolved here, once, so the frontend just displays it instead of keeping
            # its own copy of the VFR/MVFR/IFR/LIFR ordinal->label mapping
            "flight_category_label": flight_category_label(category),
            "temperature_2m": ob.get("temp"),
            "wind_speed_10m": wspd_kt * 1.852 if wspd_kt is not None else None,
        }
    return by_airport


def fetch_all_metar() -> dict:
    """Returns {icao: {visibility_mi, ceiling_ft, flight_category, flight_category_label,
    temperature_2m, wind_speed_10m}} for whichever of the 7 airports had a report in this response
    (normally all -- these are major airports with continuous ASOS/AWOS coverage). An
    airport missing from the result is just absent from the dict; callers treat that
    the same as any other missing-live-data case (model_service.predict_risk falls
    back to None -> LightGBM handles it as a missing value natively)."""
    return run_with_hard_timeout(_fetch_all, timeout=HARD_TIMEOUT_S)
