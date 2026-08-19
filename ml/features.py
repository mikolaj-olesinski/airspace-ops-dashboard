"""Feature engineering shared between the pandas prototype and the Beam pipeline.

Builds a per-flight training table from raw Eurocontrol flight records + Open-Meteo
hourly weather + METAR aviation weather + a public-holiday flag, keyed on the departure
airport (adep). Target column: delayed_15min.
"""

import holidays
import pandas as pd

# how far back to look when computing "recent congestion" signals for an airport
TRAFFIC_WINDOWS = ["1h", "3h"]

# the 7 airports we model risk for; raw data also contains flights that only
# *arrive* at one of these (adep elsewhere) since the source filter was adep OR ades
AIRPORTS = ["EDDF", "EPWA", "EGLL", "LFPG", "EHAM", "EDDM", "EPGD"]

AIRPORT_COORDS = {
    "EDDF": (50.0379, 8.5622),
    "EPWA": (52.1657, 20.9671),
    "EGLL": (51.4700, -0.4543),
    "LFPG": (49.0097, 2.5479),
    "EHAM": (52.3086, 4.7639),
    "EDDM": (48.3538, 11.7861),
    "EPGD": (54.3776, 18.4662),
}

# ISO country code per airport, used only to look up public holidays (see is_holiday
# below) -- not used anywhere else, so a plain dict is enough.
AIRPORT_COUNTRY = {
    "EDDF": "DE",
    "EDDM": "DE",
    "EPWA": "PL",
    "EPGD": "PL",
    "EGLL": "GB",
    "LFPG": "FR",
    "EHAM": "NL",
}

# cached per-country holiday calendars (holidays.country_holidays() lazily expands
# years on first lookup, so one instance per country covers any date range)
_HOLIDAY_CALENDARS = {country: holidays.country_holidays(country) for country in set(AIRPORT_COUNTRY.values())}


def is_holiday(adep: str, when) -> int:
    """1 if `when` (a date or datetime) falls on a public holiday in the airport's
    country, else 0. Holidays are a well-documented driver of air traffic delay
    patterns (leisure travel spikes, reduced staffing) that nothing else in the
    feature set captures."""
    country = AIRPORT_COUNTRY.get(adep)
    if country is None:
        return 0
    date = when.date() if hasattr(when, "date") else when
    return int(date in _HOLIDAY_CALENDARS[country])


# FAA flight-category thresholds, encoded ordinally (0=best/VFR .. 3=worst/LIFR) rather
# than as an unordered category, so a tree model can split on "worse than X" the same
# way a human reads them -- this ordering is standard aviation practice, not something
# we invented: ceiling and visibility are the two numbers that actually drive ATC
# spacing and go/no-go decisions, more directly tied to delay causes than generic
# temperature/precipitation.
FLIGHT_CATEGORIES = ["VFR", "MVFR", "IFR", "LIFR"]


def flight_category_code(visibility_mi, ceiling_ft) -> "int | None":
    if visibility_mi is None or ceiling_ft is None:
        return None
    if visibility_mi < 1 or ceiling_ft < 500:
        return 3  # LIFR
    if visibility_mi < 3 or ceiling_ft < 1000:
        return 2  # IFR
    if visibility_mi < 5 or ceiling_ft < 3000:
        return 1  # MVFR
    return 0  # VFR


def flight_category_label(code: "int | None") -> "str | None":
    """The one place VFR/MVFR/IFR/LIFR text is produced from the ordinal code -- the
    live API sends this alongside the numeric `flight_category` so the frontend just
    displays it instead of keeping its own copy of FLIGHT_CATEGORIES that could drift
    out of sync with this module."""
    return FLIGHT_CATEGORIES[code] if code is not None else None


def load_flights(path: str) -> pd.DataFrame:
    df = pd.read_parquet(
        path,
        columns=[
            "icao24",
            "flt_id",
            "adep",
            "ades",
            "first_seen",
            "typecode",
            "icao_operator",
            "duration_min",
            "expected_duration_min",
            "delay_min",
            "delayed_15min",
            "route",
        ],
    )
    # we model departure-delay risk per airport, so keep only flights that
    # actually depart from one of our 7 airports (drop arrival-only matches)
    df = df[df["adep"].isin(AIRPORTS)].reset_index(drop=True)
    return df


def load_weather(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["hour"] = pd.to_datetime(df["time"])
    df = df.rename(columns={"airport": "adep"})
    return df[["adep", "hour", "temperature_2m", "precipitation", "wind_speed_10m"]]


def load_metar(path: str) -> pd.DataFrame:
    """scripts/fetch_metar.py's output: one row per (airport, hour) with visibility,
    ceiling, and the derived flight_category, already aggregated -- see that script."""
    df = pd.read_parquet(path)
    df["hour"] = pd.to_datetime(df["hour"])
    df = df.rename(columns={"airport": "adep"})
    return df[["adep", "hour", "visibility_mi", "ceiling_ft", "flight_category"]]


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df["hour_of_day"] = df["first_seen"].dt.hour
    df["day_of_week"] = df["first_seen"].dt.dayofweek
    df["month"] = df["first_seen"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_holiday"] = df.apply(lambda r: is_holiday(r["adep"], r["first_seen"]), axis=1)
    return df


def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    df["hour"] = df["first_seen"].dt.floor("h")
    df = df.merge(weather, on=["adep", "hour"], how="left")
    return df


def add_metar_features(df: pd.DataFrame, metar: pd.DataFrame) -> pd.DataFrame:
    df["hour"] = df["first_seen"].dt.floor("h")
    df = df.merge(metar, on=["adep", "hour"], how="left")
    return df


def rolling_traffic_for_airport(df_airport: pd.DataFrame) -> pd.DataFrame:
    """Rolling departure count + delay rate for a SINGLE airport's flights, looking
    only at the past (current flight excluded via closed='left') so there is no label
    leakage from itself. Shared by the pandas prototype (per groupby group) and the
    Beam pipeline (per GroupByKey group) so the windowing logic only lives in one place.
    """
    g = df_airport.set_index("first_seen").sort_index()
    for window in TRAFFIC_WINDOWS:
        g[f"traffic_{window}"] = g["delayed_15min"].rolling(window, closed="left").count()
        g[f"delay_rate_{window}"] = g["delayed_15min"].rolling(window, closed="left").mean()
    return g.reset_index()


def add_traffic_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["adep", "first_seen"]).reset_index(drop=True)

    parts = [
        rolling_traffic_for_airport(group)
        for _, group in df.groupby("adep", sort=False)
    ]
    out = pd.concat(parts, ignore_index=True)

    for window in TRAFFIC_WINDOWS:
        out[f"traffic_{window}"] = out[f"traffic_{window}"].fillna(0)
        # no prior flights yet at an airport -> assume neutral (average) risk
        out[f"delay_rate_{window}"] = out[f"delay_rate_{window}"].fillna(
            out["delayed_15min"].mean()
        )

    return out


def build_features(flights: pd.DataFrame, weather: pd.DataFrame, metar: pd.DataFrame) -> pd.DataFrame:
    df = flights.copy()
    df = add_time_features(df)
    df = add_weather_features(df, weather)
    df = add_metar_features(df, metar)
    df = add_traffic_features(df)
    df = df.drop(columns=["hour"])
    return df


FEATURE_COLUMNS = [
    "adep",
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
    "is_holiday",
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "visibility_mi",
    "ceiling_ft",
    "flight_category",
    "traffic_1h",
    "traffic_3h",
    "delay_rate_1h",
    "delay_rate_3h",
    "typecode",
]
TARGET_COLUMN = "delayed_15min"
