import pandas as pd
from datasets import load_dataset

AIRPORTS = {"EDDF", "EPWA", "EGLL", "LFPG", "EHAM", "EDDM", "EPGD"}
SAMPLE_SIZE = 50_000

def main():
    ds = load_dataset("345rf4gt56t4r3e3/flight-delays-europe-2023-2025", split="train", streaming=True)
    df = pd.DataFrame(ds.take(SAMPLE_SIZE))

    mask = df["adep"].isin(AIRPORTS) | df["ades"].isin(AIRPORTS)
    matched = df[mask]

    print(f"sampled rows: {len(df)}")
    print(f"rows touching our airports: {len(matched)} ({len(matched) / len(df):.2%})")
    print()
    print("per-airport flight counts (as adep or ades):")
    for code in sorted(AIRPORTS):
        count = ((df["adep"] == code) | (df["ades"] == code)).sum()
        print(f"  {code}: {count}")
    print()
    print("delayed_15min rate within matched rows:")
    print(matched["delayed_15min"].value_counts(normalize=True))

if __name__ == "__main__":
    main()
