import pandas as pd
from datasets import load_dataset

def main():
    ds = load_dataset("345rf4gt56t4r3e3/flight-delays-europe-2023-2025", split="train", streaming=True)
    df = pd.DataFrame(ds.take(5000))

    print(f"rows sampled: {len(df)}")
    print(f"columns: {list(df.columns)}")
    print()
    print(df.head())
    print()
    if "delayed_15min" in df.columns:
        print("delayed_15min distribution:")
        print(df["delayed_15min"].value_counts(normalize=True))

if __name__ == "__main__":
    main()
