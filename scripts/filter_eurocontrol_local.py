import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

AIRPORTS = ["EDDF", "EPWA", "EGLL", "LFPG", "EHAM", "EDDM", "EPGD"]
OUT_DIR = Path("data/raw/eurocontrol_filtered")


def main():
    local_path = hf_hub_download(
        repo_id="345rf4gt56t4r3e3/flight-delays-europe-2023-2025",
        repo_type="dataset",
        filename="merged_flights_with_delay_2023_2025.parquet",
    )
    print(f"reading from local cache: {local_path}", flush=True)

    dataset = ds.dataset(local_path, format="parquet")
    total_rows = dataset.count_rows()
    print(f"total rows in file: {total_rows:,}", flush=True)

    airports_arr = pa.array(AIRPORTS)
    filter_expr = pc.field("adep").isin(airports_arr) | pc.field("ades").isin(airports_arr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob("*.parquet"):
        f.unlink()

    start = time.time()
    matched_total = 0
    part_idx = 0
    print("starting scan...", flush=True)
    scanner = dataset.scanner(filter=filter_expr, batch_size=100_000)
    for batch in scanner.to_batches():
        if batch.num_rows == 0:
            continue
        table = pa.Table.from_batches([batch])
        part_path = OUT_DIR / f"part_{part_idx:04d}.parquet"
        pq.write_table(table, part_path)
        matched_total += batch.num_rows
        part_idx += 1
        print(f"  wrote {part_path} ({batch.num_rows:,} rows, {matched_total:,} so far)", flush=True)

    elapsed = time.time() - start
    print(
        f"DONE. total rows: {total_rows:,} | matched: {matched_total:,} "
        f"({matched_total / total_rows:.1%}) | {elapsed:.0f}s | {part_idx} parts written",
        flush=True,
    )


if __name__ == "__main__":
    main()
