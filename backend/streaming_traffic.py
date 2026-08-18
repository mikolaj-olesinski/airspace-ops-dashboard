"""Genuine Beam windowed computation of live per-airport traffic, replacing the crude
"how many aircraft are within radius X right now" proxy that model_service.py
previously used for traffic_1h/traffic_3h.

This is a real gap worth being honest about: model_service.py's docstring already
documents that live traffic_1h/3h couldn't be a true rolling window because a single
OpenSky snapshot has no history in it. But we DO now have history -- live_state_cache.py
has been accumulating buffered snapshots (~1h, one every 12s) since server startup. This
module reprocesses that buffer through Beam's actual windowing model (SlidingWindows)
to get a real "distinct aircraft seen near this airport in the trailing N minutes"
count, instead of a single-instant proxy.

Honest caveat on "streaming": OpenSky's anonymous tier gives snapshots, not an
unbounded push stream, so there's no Pub/Sub/Kafka source to attach an actual
streaming Beam job to here. What this DOES demonstrate faithfully is Beam's windowing
semantics (SlidingWindows, per-key distinct-count-in-window) -- the same transform
code that would run against a real unbounded source unchanged, just fed from a
periodically-reprocessed bounded buffer instead. That's genuinely how you'd prototype
and unit-test a streaming Beam pipeline's logic before wiring it to a live source.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apache_beam as beam
from apache_beam.io.textio import WriteToText
from apache_beam.options.pipeline_options import PipelineOptions

from ml.features import AIRPORT_COORDS

RADIUS_DEG = 0.5  # matches opensky_client.count_aircraft_near's default
WINDOW_PERIOD_S = 300  # granularity of the sliding window; coarser is fine since we
# only ever look at the single most-recent window each time this reruns
WINDOWS = {"1h": 3600, "3h": 10800}


def _sightings(snapshots: list[dict]):
    for snap in snapshots:
        for a in snap["aircraft"]:
            lat, lon = a.get("latitude"), a.get("longitude")
            if lat is None or lon is None:
                continue
            for code, (alat, alon) in AIRPORT_COORDS.items():
                if abs(lat - alat) <= RADIUS_DEG and abs(lon - alon) <= RADIUS_DEG:
                    yield {"airport": code, "icao24": a["icao24"], "time": float(snap["time"])}


class _AttachWindowEnd(beam.DoFn):
    """Beam's grouping transforms are window-aware, but the window boundaries aren't
    part of the output value by default -- this pulls them back out via WindowParam so
    we can pick the single most-recent (i.e. "current") window afterwards."""

    def process(self, element, window=beam.DoFn.WindowParam):
        airport, count = element
        yield {"airport": airport, "count": count, "window_end": window.end.micros / 1e6}


def compute_rolling_traffic(snapshots: list[dict]) -> dict[str, dict[str, int]]:
    """snapshots: the buffered live-state history from live_state_cache.py, oldest
    first. Returns {airport: {"traffic_1h": n, "traffic_3h": n}} -- distinct aircraft
    seen within RADIUS_DEG of that airport at any point in the trailing window, as of
    the latest snapshot's timestamp."""
    if not snapshots:
        return {code: {f"traffic_{label}": 0 for label in WINDOWS} for code in AIRPORT_COORDS}

    latest_time = snapshots[-1]["time"]
    sightings = list(_sightings(snapshots))

    # DirectRunner here actually executes via Beam's portable "Prism" runner, whose
    # workers run in a separate process from this one -- a Python list captured by
    # closure (e.g. beam.Map(some_list.append)) silently never gets the results back,
    # since the append happens in the worker process's own memory. A real sink
    # (WriteToText, read back after the pipeline finishes) works regardless of which
    # process the workers actually run in.
    with tempfile.TemporaryDirectory() as tmpdir:
        out_prefix = str(Path(tmpdir) / "windows")

        options = PipelineOptions(["--runner=DirectRunner"])
        with beam.Pipeline(options=options) as p:
            keyed = (
                p
                | "Create" >> beam.Create(sightings)
                | "Timestamp"
                >> beam.Map(lambda r: beam.window.TimestampedValue((r["airport"], r["icao24"]), r["time"]))
            )

            per_label = []
            for label, size_s in WINDOWS.items():
                per_label.append(
                    keyed
                    | f"Window_{label}" >> beam.WindowInto(beam.window.SlidingWindows(size_s, WINDOW_PERIOD_S))
                    | f"Distinct_{label}" >> beam.Distinct()
                    | f"KeyByAirport_{label}" >> beam.Map(lambda kv: kv[0])
                    | f"CountPerAirport_{label}" >> beam.combiners.Count.PerElement()
                    | f"AttachWindow_{label}" >> beam.ParDo(_AttachWindowEnd())
                    | f"TagLabel_{label}" >> beam.Map(lambda r, l=label: {**r, "label": l})
                )

            (
                tuple(per_label)
                | "FlattenLabels" >> beam.Flatten()
                | "ToJSON" >> beam.Map(json.dumps)
                | "Write" >> WriteToText(out_prefix, file_name_suffix=".jsonl", num_shards=1)
            )

        collected = []
        for path in Path(tmpdir).glob("windows-*.jsonl"):
            with open(path) as f:
                collected = [json.loads(line) for line in f if line.strip()]

    # each label produces one result per sliding window covering the data; keep only
    # the window ending closest to (but not after) the latest snapshot -- that's "now"
    best: dict[tuple[str, str], dict] = {}
    for r in collected:
        key = (r["airport"], r["label"])
        if r["window_end"] > latest_time + WINDOW_PERIOD_S:
            continue  # window extends past the data we actually have -- not "current"
        if key not in best or r["window_end"] > best[key]["window_end"]:
            best[key] = r

    result = {code: {f"traffic_{label}": 0 for label in WINDOWS} for code in AIRPORT_COORDS}
    for (airport, label), r in best.items():
        result[airport][f"traffic_{label}"] = r["count"]
    return result
