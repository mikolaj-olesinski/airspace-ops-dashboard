import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Aircraft, AirportPrediction } from "../lib/types";
import { AIRPORT_COORDS } from "../lib/airports";

const RISK_COLOR: Record<string, string> = {
  low: "#8b8f98",
  medium: "#f5a623",
  high: "#f0563a",
};

type Pos = { lon: number; lat: number; heading: number };

function makePlaneIcon(): ImageData {
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
  ctx.fillStyle = "#e5e7eb";
  ctx.fill();
  return ctx.getImageData(0, 0, s, s);
}

function aircraftToFeatures(positions: Map<string, Pos>) {
  return {
    type: "FeatureCollection" as const,
    features: Array.from(positions.entries()).map(([id, p]) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
      properties: { id, heading: p.heading },
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

interface MapViewProps {
  aircraft: Aircraft[];
  predictions: AirportPrediction[];
}

export default function MapView({ aircraft, predictions }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const prevPos = useRef<Map<string, Pos>>(new Map());
  const targetPos = useRef<Map<string, Pos>>(new Map());
  const animFrame = useRef<number | null>(null);
  const predictionsRef = useRef(predictions);
  predictionsRef.current = predictions;

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
      map.addImage("plane", makePlaneIcon());

      map.addSource("aircraft", { type: "geojson", data: aircraftToFeatures(new Map()) });
      map.addLayer({
        id: "aircraft-glow",
        type: "circle",
        source: "aircraft",
        paint: {
          "circle-radius": 9,
          "circle-color": "#e5e7eb",
          "circle-opacity": 0.08,
          "circle-blur": 1,
        },
      });
      map.addLayer({
        id: "aircraft-icons",
        type: "symbol",
        source: "aircraft",
        layout: {
          "icon-image": "plane",
          "icon-size": 0.5,
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

  // animate aircraft positions smoothly between polls instead of snapping
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const nextTarget = new Map<string, Pos>();
    for (const a of aircraft) {
      if (a.latitude == null || a.longitude == null) continue;
      nextTarget.set(a.icao24, {
        lon: a.longitude,
        lat: a.latitude,
        heading: a.true_track ?? 0,
      });
    }

    prevPos.current = targetPos.current.size ? new Map(targetPos.current) : new Map(nextTarget);
    targetPos.current = nextTarget;

    if (animFrame.current) cancelAnimationFrame(animFrame.current);
    const durationMs = 11_000; // just under the 12s poll interval
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
      src?.setData(aircraftToFeatures(interpolated));

      if (t < 1) animFrame.current = requestAnimationFrame(step);
    };
    animFrame.current = requestAnimationFrame(step);

    return () => {
      if (animFrame.current) cancelAnimationFrame(animFrame.current);
    };
  }, [aircraft]);

  return <div ref={containerRef} className="h-full w-full" />;
}
