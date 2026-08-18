import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Aircraft, AirportPrediction } from "../lib/types";
import type { Snapshot } from "../lib/history";
import { AIRPORT_COORDS } from "../lib/airports";
import TimeSlider from "./TimeSlider";

const RISK_COLOR: Record<string, string> = {
  low: "#8b8f98",
  medium: "#f5a623",
  high: "#f0563a",
};

const TRAIL_LENGTH = 15;

type Pos = { lon: number; lat: number; heading: number };
type Selection =
  | { kind: "aircraft"; id: string }
  | { kind: "airport"; code: string }
  | null;

function makePlaneIcon(fill: string): ImageData {
  const s = 32;
  const canvas = document.createElement("canvas");
  canvas.width = s;
  canvas.height = s;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(s / 2, s / 2);
  ctx.beginPath();
  ctx.moveTo(0, -11);
  ctx.lineTo(8, 10);
  ctx.lineTo(0, 5);
  ctx.lineTo(-8, 10);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  return ctx.getImageData(0, 0, s, s);
}

function aircraftToFeatures(positions: Map<string, Pos>, selectedId: string | null) {
  return {
    type: "FeatureCollection" as const,
    features: Array.from(positions.entries()).map(([id, p]) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
      properties: { id, heading: p.heading, selected: id === selectedId ? 1 : 0 },
    })),
  };
}

function airportFeatures(predictions: AirportPrediction[]) {
  const byCode = new Map(predictions.map((p) => [p.airport, p]));
  return {
    type: "FeatureCollection" as const,
    features: Object.entries(AIRPORT_COORDS).map(([code, [lat, lon]]) => {
      const p = byCode.get(code);
      return {
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [lon, lat] },
        properties: {
          code,
          color: p ? RISK_COLOR[p.risk_level] : "#4b5563",
          risk: p ? Math.round(p.risk_score * 100) : null,
        },
      };
    }),
  };
}

function emptyLine() {
  return { type: "FeatureCollection" as const, features: [] as GeoJSON.Feature[] };
}

interface MapViewProps {
  aircraft: Aircraft[];
  predictions: AirportPrediction[];
  /** how long the position-interpolation animation should take to reach the new
   * aircraft prop -- long (matching the poll interval) when tracking live data, short
   * when stepping through history during scrub/playback so movement stays visible */
  transitionMs?: number;
  history: Snapshot[];
  scrubIndex: number | null;
  playing: boolean;
  onScrub: (index: number) => void;
  onTogglePlay: () => void;
  onGoLive: () => void;
}

export default function MapView({
  aircraft,
  predictions,
  transitionMs = 11_000,
  history,
  scrubIndex,
  playing,
  onScrub,
  onTogglePlay,
  onGoLive,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const prevPos = useRef<Map<string, Pos>>(new Map());
  const targetPos = useRef<Map<string, Pos>>(new Map());
  const trailHistory = useRef<Map<string, [number, number][]>>(new Map());
  const animFrame = useRef<number | null>(null);
  const predictionsRef = useRef(predictions);
  predictionsRef.current = predictions;
  const aircraftById = useRef<Map<string, Aircraft>>(new Map());

  const [selected, setSelected] = useState<Selection>(null);
  const selectedRef = useRef<Selection>(null);
  selectedRef.current = selected;

  // map init (once)
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [10, 50.5],
      zoom: 4.3,
      attributionControl: false,
    });
    mapRef.current = map;

    map.on("load", () => {
      map.addImage("plane", makePlaneIcon("#e5e7eb"));
      map.addImage("plane-selected", makePlaneIcon("#60a5fa"));

      map.addSource("trail", { type: "geojson", data: emptyLine() });
      map.addLayer({
        id: "trail-line",
        type: "line",
        source: "trail",
        paint: {
          "line-color": "#60a5fa",
          "line-width": 1.5,
          "line-opacity": 0.6,
          "line-dasharray": [1, 1.5],
        },
      });

      map.addSource("aircraft", { type: "geojson", data: aircraftToFeatures(new Map(), null) });
      map.addLayer({
        id: "aircraft-glow",
        type: "circle",
        source: "aircraft",
        paint: {
          "circle-radius": ["case", ["==", ["get", "selected"], 1], 14, 9],
          "circle-color": ["case", ["==", ["get", "selected"], 1], "#60a5fa", "#e5e7eb"],
          "circle-opacity": ["case", ["==", ["get", "selected"], 1], 0.18, 0.08],
          "circle-blur": 1,
        },
      });
      map.addLayer({
        id: "aircraft-icons",
        type: "symbol",
        source: "aircraft",
        layout: {
          "icon-image": ["case", ["==", ["get", "selected"], 1], "plane-selected", "plane"],
          "icon-size": ["case", ["==", ["get", "selected"], 1], 0.65, 0.5],
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
      });

      map.addSource("airports", { type: "geojson", data: airportFeatures(predictionsRef.current) });
      map.addLayer({
        id: "airport-rings",
        type: "circle",
        source: "airports",
        paint: {
          "circle-radius": 16,
          "circle-color": ["get", "color"],
          "circle-opacity": 0.12,
        },
      });
      map.addLayer({
        id: "airport-dots",
        type: "circle",
        source: "airports",
        paint: {
          "circle-radius": 4,
          "circle-color": ["get", "color"],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#08090a",
        },
      });
      map.addLayer({
        id: "airport-labels",
        type: "symbol",
        source: "airports",
        layout: {
          "text-field": ["get", "code"],
          "text-size": 10,
          "text-offset": [0, 1.3],
          "text-font": ["Open Sans Regular"],
        },
        paint: { "text-color": "#9ca3af" },
      });

      const clickableLayers = ["aircraft-icons", "aircraft-glow", "airport-dots", "airport-rings"];
      for (const layer of clickableLayers) {
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }

      map.on("click", (e) => {
        const hits = map.queryRenderedFeatures(e.point, {
          layers: clickableLayers,
        });
        if (hits.length === 0) {
          setSelected(null);
          return;
        }
        const hit = hits[0];
        if (hit.layer.id.startsWith("aircraft")) {
          setSelected({ kind: "aircraft", id: hit.properties!.id as string });
        } else {
          setSelected({ kind: "airport", code: hit.properties!.code as string });
        }
      });
    });

    return () => {
      if (animFrame.current) cancelAnimationFrame(animFrame.current);
      map.remove();
    };
  }, []);

  // update airport risk colors when predictions change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("airports") as maplibregl.GeoJSONSource | undefined;
    src?.setData(airportFeatures(predictions));
  }, [predictions]);

  // clear the selected aircraft's trail if it's no longer selected
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource("trail")) return;
    const src = map.getSource("trail") as maplibregl.GeoJSONSource;
    if (selected?.kind !== "aircraft") {
      src.setData(emptyLine());
      return;
    }
    const history = trailHistory.current.get(selected.id);
    if (history && history.length >= 2) {
      src.setData({
        type: "FeatureCollection",
        features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: history } }],
      });
    }
  }, [selected]);

  // animate aircraft positions smoothly between polls instead of snapping
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    aircraftById.current = new Map(aircraft.map((a) => [a.icao24, a]));

    const nextTarget = new Map<string, Pos>();
    for (const a of aircraft) {
      if (a.latitude == null || a.longitude == null) continue;
      nextTarget.set(a.icao24, {
        lon: a.longitude,
        lat: a.latitude,
        heading: a.true_track ?? 0,
      });

      const hist = trailHistory.current.get(a.icao24) ?? [];
      hist.push([a.longitude, a.latitude]);
      if (hist.length > TRAIL_LENGTH) hist.shift();
      trailHistory.current.set(a.icao24, hist);
    }

    prevPos.current = targetPos.current.size ? new Map(targetPos.current) : new Map(nextTarget);
    targetPos.current = nextTarget;

    if (animFrame.current) cancelAnimationFrame(animFrame.current);
    const durationMs = transitionMs;
    const start = performance.now();

    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 2);
      const interpolated = new Map<string, Pos>();

      for (const [id, target] of targetPos.current) {
        const from = prevPos.current.get(id) ?? target;
        interpolated.set(id, {
          lon: from.lon + (target.lon - from.lon) * eased,
          lat: from.lat + (target.lat - from.lat) * eased,
          heading: target.heading,
        });
      }

      const src = map.getSource("aircraft") as maplibregl.GeoJSONSource | undefined;
      src?.setData(aircraftToFeatures(interpolated, selectedRef.current?.kind === "aircraft" ? selectedRef.current.id : null));

      if (t < 1) animFrame.current = requestAnimationFrame(step);
    };
    animFrame.current = requestAnimationFrame(step);

    return () => {
      if (animFrame.current) cancelAnimationFrame(animFrame.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aircraft, transitionMs]);

  const selectedAircraft = selected?.kind === "aircraft" ? aircraftById.current.get(selected.id) : null;
  const selectedAirport =
    selected?.kind === "airport" ? predictions.find((p) => p.airport === selected.code) : null;

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {selected?.kind === "aircraft" && (
        <div className="fade-in tick-corners absolute top-3 left-3 w-56 border border-[var(--panel-border-strong)] bg-[#0a0b0cf0] p-3 backdrop-blur-sm">
          <div className="flex items-start justify-between">
            <span className="font-num text-sm font-semibold text-[#60a5fa]">
              {selectedAircraft?.callsign?.trim() || selected.id.toUpperCase()}
            </span>
            <button onClick={() => setSelected(null)} className="text-[var(--text-dim)] hover:text-white">
              ✕
            </button>
          </div>
          {selectedAircraft ? (
            <dl className="mt-2 space-y-1 text-[11px]">
              <Row label="origin" value={selectedAircraft.origin_country} />
              <Row
                label="altitude"
                value={selectedAircraft.baro_altitude != null ? `${Math.round(selectedAircraft.baro_altitude)} m` : "n/a"}
              />
              <Row
                label="speed"
                value={selectedAircraft.velocity != null ? `${Math.round(selectedAircraft.velocity * 3.6)} km/h` : "n/a"}
              />
              <Row label="heading" value={selectedAircraft.true_track != null ? `${Math.round(selectedAircraft.true_track)}°` : "n/a"} />
              <Row label="icao24" value={selected.id} />
            </dl>
          ) : (
            <p className="mt-2 text-[11px] text-[var(--text-dim)]">left radar coverage</p>
          )}
        </div>
      )}

      {selected?.kind === "airport" && (
        <div className="fade-in tick-corners absolute bottom-3 left-3 w-56 border border-[var(--panel-border-strong)] bg-[#0a0b0cf0] p-3 backdrop-blur-sm">
          <div className="flex items-start justify-between">
            <span className="font-num text-sm font-semibold text-white">{selected.code}</span>
            <button onClick={() => setSelected(null)} className="text-[var(--text-dim)] hover:text-white">
              ✕
            </button>
          </div>
          {selectedAirport ? (
            <dl className="mt-2 space-y-1 text-[11px]">
              <Row label="risk score" value={`${Math.round(selectedAirport.risk_score * 100)}%`} />
              <Row label="risk level" value={selectedAirport.risk_level} />
              <Row label="live traffic" value={`${selectedAirport.live_traffic_count} aircraft`} />
              <Row
                label="wind"
                value={selectedAirport.weather.wind_speed_10m != null ? `${selectedAirport.weather.wind_speed_10m} km/h` : "n/a"}
              />
              <Row
                label="temp"
                value={selectedAirport.weather.temperature_2m != null ? `${selectedAirport.weather.temperature_2m}°C` : "n/a"}
              />
            </dl>
          ) : (
            <p className="mt-2 text-[11px] text-[var(--text-dim)]">waiting for prediction...</p>
          )}
        </div>
      )}

      <TimeSlider
        history={history}
        scrubIndex={scrubIndex}
        playing={playing}
        onScrub={onScrub}
        onTogglePlay={onTogglePlay}
        onGoLive={onGoLive}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-[var(--text-dim)]">{label}</dt>
      <dd className="font-num text-[#d1d5db]">{value}</dd>
    </div>
  );
}
