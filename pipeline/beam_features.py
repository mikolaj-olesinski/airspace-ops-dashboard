"""Apache Beam batch pipeline: raw Eurocontrol flights + Open-Meteo weather -> training
features (data/processed/features-*.parquet).

Same feature logic as prototyped and validated (on the full dataset) in
scripts/prototype_features.py, expressed here as Beam transforms and run locally on
DirectRunner:
  - beam.Map / beam.Filter  -> per-flight row cleanup, time features, weather join
  - beam.CombinePerKey      -> mean delay rate per airport (used as the cold-start
                                fill value for the rolling window features below)
  - beam.GroupByKey         -> group each airport's flights together so the rolling
                                traffic/delay-rate windows can be computed in order

Split into two stages (extract, then transform) rather than one end-to-end pipeline:
Prism (the local portable runner) processes on the order of ~5k rows/sec per-element on
this machine, so a single job over all ~4M raw flight rows takes too long for one run.
extract() does the cheap per-row work (filter/time-features/weather-join) and can be run
in file-count chunks independently. transform() then does the rolling-window step ONCE
over the full combined output of extract() -- this matters for correctness, not just
speed: the source part files are only loosely chronological (adjacent chunks' date
ranges overlap by about a month), so computing rolling windows separately per chunk
would silently under-count recent traffic near each chunk boundary.
"""

import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apache_beam as beam
import pandas as pd
import pyarrow as pa
from apache_beam.io.parquetio import ReadFromParquet, WriteToParquet
from apache_beam.options.pipeline_options import PipelineOptions

from ml.features import AIRPORTS, TRAFFIC_WINDOWS, rolling_traffic_for_airport

FLIGHTS_GLOB = "data/raw/eurocontrol_filtered/part_*.parquet"
WEATHER_PATH = "data/raw/weather_2023_2025.parquet"
EXTRACTED_GLOB = "data/processed/_extracted_shard*.parquet"
OUT_PATH_PREFIX = "data/processed/features"

FLIGHT_COLUMNS = [
    "adep",
    "ades",
    "first_seen",
    "typecode",
    "duration_min",
    "expected_duration_min",
    "delay_min",
    "delayed_15min",
    "route",
]

EXTRACTED_SCHEMA = pa.schema(
    [
        ("adep", pa.string()),
        ("first_seen", pa.timestamp("us")),
        ("hour_of_day", pa.int64()),
        ("day_of_week", pa.int64()),
        ("month", pa.int64()),
        ("is_weekend", pa.int64()),
        ("temperature_2m", pa.float64()),
        ("precipitation", pa.float64()),
        ("wind_speed_10m", pa.float64()),
        ("typecode", pa.string()),
        ("delayed_15min", pa.int64()),
    ]
)

OUTPUT_SCHEMA = pa.schema(
    [
        ("adep", pa.string()),
        ("first_seen", pa.timestamp("us")),
        ("hour_of_day", pa.int64()),
        ("day_of_week", pa.int64()),
        ("month", pa.int64()),
        ("is_weekend", pa.int64()),
        ("temperature_2m", pa.float64()),
        ("precipitation", pa.float64()),
        ("wind_speed_10m", pa.float64()),
        ("traffic_1h", pa.float64()),
        ("traffic_3h", pa.float64()),
        ("delay_rate_1h", pa.float64()),
        ("delay_rate_3h", pa.float64()),
        ("typecode", pa.string()),
        ("delayed_15min", pa.int64()),
    ]
)


def add_time_features_row(row: dict) -> dict:
    ts = row["first_seen"]
    row = dict(row)
    row["hour_of_day"] = ts.hour
    row["day_of_week"] = ts.dayofweek
    row["month"] = ts.month
    row["is_weekend"] = int(row["day_of_week"] in (5, 6))
    return row


def weather_key(adep: str, first_seen) -> tuple:
    # Open-Meteo's hourly timestamps look like "2023-01-01T00:00" -> reuse that
    # format as the join key instead of parsing weather['time'] back to a datetime.
    return (adep, first_seen.strftime("%Y-%m-%dT%H:00"))


def join_weather_row(row: dict, weather_lookup: dict) -> dict:
    row = dict(row)
    weather = weather_lookup.get(weather_key(row["adep"], row["first_seen"]))
    row["temperature_2m"] = weather["temperature_2m"] if weather else None
    row["precipitation"] = weather["precipitation"] if weather else None
    row["wind_speed_10m"] = weather["wind_speed_10m"] if weather else None
    return row


def compute_rolling_features(element, mean_delay_by_airport: dict):
    adep, rows = element
    df = pd.DataFrame(rows)
    df = rolling_traffic_for_airport(df)

    fill_value = mean_delay_by_airport.get(adep, 0.0)
    for window in TRAFFIC_WINDOWS:
        df[f"traffic_{window}"] = df[f"traffic_{window}"].fillna(0)
        df[f"delay_rate_{window}"] = df[f"delay_rate_{window}"].fillna(fill_value)

    # pandas NaN (e.g. missing typecode) isn't valid in a pyarrow string column -> None
    df = df.astype(object).where(pd.notnull(df), None)
    yield from df.to_dict("records")


def extract(file_paths=None, out_path_prefix="data/processed/_extracted_shard"):
    """Stage 1: filter to our airports, add time features, join weather. Cheap
    per-row work; safe to run over an arbitrary subset of the raw part files."""
    if file_paths is None:
        file_paths = sorted(glob.glob(FLIGHTS_GLOB))

    options = PipelineOptions(["--runner=DirectRunner", "--job_server_timeout=1800"])

    with beam.Pipeline(options=options) as p:
        weather_lookup = (
            p
            | "ReadWeather" >> ReadFromParquet(WEATHER_PATH)
            | "WeatherToKV"
            >> beam.Map(
                lambda row: (
                    (row["airport"], row["time"]),
                    {
                        "temperature_2m": row["temperature_2m"],
                        "precipitation": row["precipitation"],
                        "wind_speed_10m": row["wind_speed_10m"],
                    },
                )
            )
        )

        flight_sources = [
            p | f"ReadFlights_{i}" >> ReadFromParquet(path, columns=FLIGHT_COLUMNS)
            for i, path in enumerate(file_paths)
        ]

        (
            tuple(flight_sources)
            | "FlattenFlights" >> beam.Flatten()
            | "FilterOurAirports" >> beam.Filter(lambda row: row["adep"] in AIRPORTS)
            | "AddTimeFeatures" >> beam.Map(add_time_features_row)
            | "JoinWeather"
            >> beam.Map(join_weather_row, weather_lookup=beam.pvalue.AsDict(weather_lookup))
            | "SelectExtractedColumns"
            >> beam.Map(lambda row: {k: row[k] for k in EXTRACTED_SCHEMA.names})
            | "WriteExtracted"
            >> WriteToParquet(
                file_path_prefix=out_path_prefix,
                schema=EXTRACTED_SCHEMA,
                file_name_suffix=".parquet",
                num_shards=1,
            )
        )


def transform(extracted_glob=EXTRACTED_GLOB, out_path_prefix=OUT_PATH_PREFIX):
    """Stage 2: rolling traffic/delay-rate windows per airport, computed ONCE over the
    full combined output of extract() so the windows see each airport's complete,
    correctly-ordered flight history (no chunk-boundary gaps)."""
    extracted_files = sorted(glob.glob(extracted_glob))

    # default job_server_timeout (300s) can cut off the state stream while
    # GroupByKey is still shuffling millions of rows through the local runner
    options = PipelineOptions(["--runner=DirectRunner", "--job_server_timeout=1800"])

    with beam.Pipeline(options=options) as p:
        sources = [
            p | f"ReadExtracted_{i}" >> ReadFromParquet(path)
            for i, path in enumerate(extracted_files)
        ]
        flights = tuple(sources) | "FlattenExtracted" >> beam.Flatten()

        mean_delay_by_airport = (
            flights
            | "KeyDelayByAirport" >> beam.Map(lambda row: (row["adep"], row["delayed_15min"]))
            | "MeanDelayPerAirport" >> beam.CombinePerKey(beam.combiners.MeanCombineFn())
        )

        features = (
            flights
            | "KeyByAirport" >> beam.Map(lambda row: (row["adep"], row))
            | "GroupByAirport" >> beam.GroupByKey()
            | "ComputeRollingFeatures"
            >> beam.FlatMap(
                compute_rolling_features,
                mean_delay_by_airport=beam.pvalue.AsDict(mean_delay_by_airport),
            )
        )

        (
            features
            | "SelectOutputColumns" >> beam.Map(lambda row: {k: row[k] for k in OUTPUT_SCHEMA.names})
            | "WriteFeatures"
            >> WriteToParquet(
                file_path_prefix=out_path_prefix,
                schema=OUTPUT_SCHEMA,
                file_name_suffix=".parquet",
                num_shards=1,
            )
        )


def run():
    """Full pipeline in one process: extract() over all files, then transform().
    Works end-to-end (verified on the full dataset), but on this machine the local
    Prism runner processes on the order of ~5k rows/sec, so a single call to extract()
    over all ~4M raw rows takes ~15 minutes -- too long for one uninterrupted local run
    in this environment. In practice this was run as: extract() four times over
    consecutive ~40-file chunks of FLIGHTS_GLOB (each into its own
    data/processed/_extracted_shardN-...parquet), then transform() once over all four
    extracted shards together, so the rolling-window step still sees each airport's
    complete, correctly-ordered history."""
    extract()
    transform()


if __name__ == "__main__":
    run()
