from huggingface_hub import hf_hub_download

def main():
    path = hf_hub_download(
        repo_id="345rf4gt56t4r3e3/flight-delays-europe-2023-2025",
        repo_type="dataset",
        filename="merged_flights_with_delay_2023_2025.parquet",
    )
    print("downloaded to:", path)

if __name__ == "__main__":
    main()
