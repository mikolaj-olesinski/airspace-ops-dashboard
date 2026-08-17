import requests

BBOX = {"lamin": 49, "lomin": 5, "lamax": 55, "lomax": 24}

def main():
    resp = requests.get("https://opensky-network.org/api/states/all", params=BBOX, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    states = data.get("states") or []

    print(f"timestamp: {data.get('time')}")
    print(f"aircraft in bounding box: {len(states)}")
    for s in states[:5]:
        icao24, callsign, origin_country = s[0], s[1], s[2]
        lon, lat, baro_altitude = s[5], s[6], s[7]
        print(f"  {icao24} {callsign!r:12} {origin_country:20} lon={lon} lat={lat} alt={baro_altitude}")

if __name__ == "__main__":
    main()
