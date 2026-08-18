export interface Aircraft {
  icao24: string;
  callsign: string | null;
  origin_country: string;
  longitude: number | null;
  latitude: number | null;
  baro_altitude: number | null;
  on_ground: boolean;
  velocity: number | null;
  true_track: number | null;
  vertical_rate: number | null;
  geo_altitude: number | null;
}

export interface LiveStates {
  time: number;
  aircraft: Aircraft[];
}

export type RiskLevel = "low" | "medium" | "high";

export interface AirportPrediction {
  airport: string;
  risk_score: number;
  risk_level: RiskLevel;
  live_traffic_count: number;
  weather: {
    temperature_2m: number | null;
    precipitation: number | null;
    wind_speed_10m: number | null;
  };
}

export interface Predictions {
  computed_at: number;
  predictions: AirportPrediction[];
}
