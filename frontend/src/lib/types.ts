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

export interface TopFactor {
  feature: string;
  label: string;
  value: string;
  contribution: number;
  direction: "increases" | "decreases";
}

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
  // null when aviationweather.gov's METAR API was unavailable for this poll
  metar: {
    visibility_mi: number | null;
    ceiling_ft: number | null;
    flight_category: number | null; // 0=VFR, 1=MVFR, 2=IFR, 3=LIFR -- see flight_category_label for the text
    flight_category_label: string | null;
  } | null;
  top_factors: TopFactor[];
}

export interface Predictions {
  computed_at: number;
  predictions: AirportPrediction[];
}

export interface Briefing {
  briefing: string;
  generated_at: number;
}

export interface AirportBriefing {
  briefing: string;
  generated_at: number;
  airport: string;
}

export interface AircraftRisk {
  airport: string;
  risk_score: number;
  risk_level: RiskLevel;
  live_traffic_count: number;
  top_factors: TopFactor[];
  icao24: string;
  nearest_airport: string;
  aircraft_info: {
    typecode: string | null;
    manufacturer: string | null;
    model: string | null;
    operator: string | null;
    registration: string | null;
  };
}

export interface PredictionsSnapshot {
  time: number;
  predictions: AirportPrediction[];
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}
