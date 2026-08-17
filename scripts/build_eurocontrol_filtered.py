import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from datasets import load_dataset

AIRPORTS = {"EDDF", "EPWA", "EGLL", "LFPG", "EHAM", "EDDM", "EPGD"}
OUT_DIR = Path("data/raw/eurocontrol_filtered")
FLUSH_EVERY = 200_000
LOG_EVERY = 1_000_000


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ds = load_dataset("345rf4gt56t4r3e3/flight-delays-europe-2023-2025", split="train", streaming=True)

    buffer = []
    part_idx = 0
    total = 0
    matched_total = 0
    start = time.time()

    def flush():
        nonlocal buffer, part_idx
        if not buffer:
            return
        table = pa.Table.from_pylist(buffer)
        part_path = OUT_DIR / f"part_{part_idx:04d}.parquet"
        pq.write_table(table, part_path)
        print(f"  wrote {part_path} ({len(buffer):,} rows)", flush=True)
        part_idx += 1
        buffer = []

    for row in ds:
        total += 1
        if row["adep"] in AIRPORTS or row["ades"] in AIRPORTS:
            buffer.append(row)
            matched_total += 1

        if len(buffer) >= FLUSH_EVERY:
            flush()

        if total % LOG_EVERY == 0:
            elapsed = time.time() - start
            print(
                f"processed {total:,} rows | matched {matched_total:,} "
                f"({matched_total / total:.1%}) | {elapsed:.0f}s elapsed | "
                f"{total / elapsed:.0f} rows/s",
                flush=True,
            )

    flush()

    elapsed = time.time() - start
    print(
        f"DONE. total rows: {total:,} | matched: {matched_total:,} "
        f"({matched_total / total:.1%}) | {elapsed:.0f}s | {part_idx} parts written",
        flush=True,
    )


if __name__ == "__main__":
    main()
