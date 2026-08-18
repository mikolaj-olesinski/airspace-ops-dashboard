"""Feature engineering shared between the pandas prototype and the Beam pipeline.

Builds a per-flight training table from raw Eurocontrol flight records + Open-Meteo
hourly weather, keyed on the departure airport (adep). Target column: delayed_15min.
"""

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


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df["hour_of_day"] = df["first_seen"].dt.hour
    df["day_of_week"] = df["first_seen"].dt.dayofweek
    df["month"] = df["first_seen"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    return df


def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    df["hour"] = df["first_seen"].dt.floor("h")
    df = df.merge(weather, on=["adep", "hour"], how="left")
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


def build_features(flights: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    df = flights.copy()
    df = add_time_features(df)
    df = add_weather_features(df, weather)
    df = add_traffic_features(df)
    df = df.drop(columns=["hour"])
    return df


FEATURE_COLUMNS = [
    "adep",
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "traffic_1h",
    "traffic_3h",
    "delay_rate_1h",
    "delay_rate_3h",
    "typecode",
]
TARGET_COLUMN = "delayed_15min"
