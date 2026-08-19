import { useEffect, useRef, useState, type ReactNode } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Aircraft, AirportPrediction, PredictionsSnapshot } from "../lib/types";
import type { Snapshot } from "../lib/history";
import { AIRPORT_COORDS } from "../lib/airports";
import { useAircraftRisk } from "../lib/api";
import TimeSlider from "./TimeSlider";
import Sparkline from "./Sparkline";

const RISK_COLOR: Record<string, string> = {
  low: "#8b8f98",
  medium: "#f5a623",
  high: "#f0563a",
};

// indexed by the numeric flight_category (0=VFR best .. 3=LIFR worst) the API returns
// -- the label text itself comes from the API too (flight_category_label), not
// duplicated here; this is just the presentation color per severity level
const FLIGHT_CATEGORY_COLOR = ["#8b8f98", "#f5a623", "#f0563a", "#d946ef"];

const TRAIL_LENGTH = 15;
// how long a freshly-polled real position takes to fully absorb into the dead-reckoned
// simulation (see the animation loop below) -- short on purpose, just enough to avoid a
// visible snap when OpenSky's real position doesn't exactly match where extrapolation
// predicted it would be
const CORRECTION_MS = 2500;

type Pos = { lon: number; lat: number; heading: number };
type Kinematic = Pos & { vLon: number; vLat: number }; // degrees per second
type Selection =
  | { kind: "aircraft"; id: string }
  | { kind: "airport"; code: string }
  | null;

/** Converts a reported ground speed (m/s) + heading (degrees, clockwise from north)
 * into a lat/lon rate of change, so aircraft can keep advancing smoothly between polls
 * at their actual reported speed instead of a fixed-duration ease toward a stale target.
 * This is exactly what real radar displays do between hits ("dead reckoning"). */
function velocityToDegPerSec(lat: number, speedMs: number, headingDeg: number) {
  if (!speedMs) return { vLon: 0, vLat: 0 };
  const rad = (headingDeg * Math.PI) / 180;
  const northMs = speedMs * Math.cos(rad);
  const eastMs = speedMs * Math.sin(rad);
  const metersPerDegLat = 111_320;
  const metersPerDegLon = 111_320 * Math.cos((lat * Math.PI) / 180);
  return { vLat: northMs / metersPerDegLat, vLon: eastMs / metersPerDegLon };
}

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
  /** true while tracking live data (dead-reckoning between polls, see the animation
   * loop below); false while scrubbing/replaying history, where each step is a discrete
   * past snapshot and a short ease -- not physics-based extrapolation -- is what should
   * carry the view between them. */
  live: boolean;
  /** ease duration between historical snapshots while scrubbing/playing back; unused
   * in live mode. */
  transitionMs?: number;
  history: Snapshot[];
  predictionsHistory: PredictionsSnapshot[];
  scrubIndex: number | null;
  playing: boolean;
  onScrub: (index: number) => void;
  onTogglePlay: () => void;
  onGoLive: () => void;
  /** the airport filter chip row (AirportFilter.tsx) -- selecting it there flies the
   * camera to that airport and opens its card; clicking an airport on the map does the
   * reverse, syncing the chip row so every other chart filters too. */
  selectedAirport?: string | null;
  onSelectAirport?: (code: string | null) => void;
  /** forwarded to TimeSlider's "next update in Xs" countdown -- see its docstring */
  pollIntervalS?: number;
}

export default function MapView({
  aircraft,
  predictions,
  live,
  transitionMs = 450,
  history,
  predictionsHistory,
  scrubIndex,
  playing,
  onScrub,
  onTogglePlay,
  onGoLive,
  selectedAirport: selectedAirportProp = null,
  onSelectAirport,
  pollIntervalS,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  // live mode: each aircraft's own extrapolated position + velocity, advanced every
  // frame (see the continuous render loop below), plus a short blend-in whenever a
  // freshly polled real position lands (correction)
  const kinematics = useRef<Map<string, Kinematic>>(new Map());
  const correction = useRef<Map<string, { fromLon: number; fromLat: number; startedAt: number }>>(new Map());
  // scrub/playback mode: the old discrete ease-between-two-snapshots approach
  const scrubPrev = useRef<Map<string, Pos>>(new Map());
  const scrubTarget = useRef<Map<string, Pos>>(new Map());
  const scrubAnimStart = useRef(0);
  const lastFrameTime = useRef<number | null>(null);
  const liveRef = useRef(live);
  liveRef.current = live;
  const transitionMsRef = useRef(transitionMs);
  transitionMsRef.current = transitionMs;

  const trailHistory = useRef<Map<string, [number, number][]>>(new Map());
  const predictionsRef = useRef(predictions);
  predictionsRef.current = predictions;
  const aircraftById = useRef<Map<string, Aircraft>>(new Map());

  const [selected, setSelected] = useState<Selection>(null);
  const selectedRef = useRef<Selection>(null);
  selectedRef.current = selected;
  const onSelectAirportRef = useRef(onSelectAirport);
  onSelectAirportRef.current = onSelectAirport;
  // tracks the airport code we last pushed to/pulled from the App-level filter, so the
  // sync effect below doesn't re-fly the camera to an airport the user just clicked
  // directly on the map (which already centered it)
  const appliedAirportRef = useRef<string | null>(null);

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
          const code = hit.properties!.code as string;
          appliedAirportRef.current = code;
          setSelected({ kind: "airport", code });
          onSelectAirportRef.current?.(code);
        }
      });
    });

    return () => {
      map.remove();
    };
  }, []);

  // continuous render loop, independent of when new poll data actually arrives: in live
  // mode it advances every aircraft's position each frame using its own reported speed
  // and heading (dead reckoning), so movement is smooth and immediate instead of a slow
  // multi-second glide toward a stale target; in scrub mode it eases between the two
  // most recent historical snapshots instead
  useEffect(() => {
    let raf: number;
    const frame = (now: number) => {
      const map = mapRef.current;
      const src = map?.getSource("aircraft") as maplibregl.GeoJSONSource | undefined;
      if (src) {
        const rendered = new Map<string, Pos>();
        if (liveRef.current) {
          const dt = lastFrameTime.current != null ? (now - lastFrameTime.current) / 1000 : 0;
          for (const [id, k] of kinematics.current) {
            k.lon += k.vLon * dt;
            k.lat += k.vLat * dt;
            let lon = k.lon;
            let lat = k.lat;
            const corr = correction.current.get(id);
            if (corr) {
              const t = Math.min(1, (now - corr.startedAt) / CORRECTION_MS);
              lon = corr.fromLon + (k.lon - corr.fromLon) * t;
              lat = corr.fromLat + (k.lat - corr.fromLat) * t;
              if (t >= 1) correction.current.delete(id);
            }
            rendered.set(id, { lon, lat, heading: k.heading });
          }
        } else {
          const t = Math.min(1, (now - scrubAnimStart.current) / transitionMsRef.current);
          const eased = 1 - Math.pow(1 - t, 2);
          for (const [id, target] of scrubTarget.current) {
            const from = scrubPrev.current.get(id) ?? target;
            rendered.set(id, {
              lon: from.lon + (target.lon - from.lon) * eased,
              lat: from.lat + (target.lat - from.lat) * eased,
              heading: target.heading,
            });
          }
        }
        src.setData(aircraftToFeatures(rendered, selectedRef.current?.kind === "aircraft" ? selectedRef.current.id : null));
      }
      lastFrameTime.current = now;
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  // feed new poll/scrub data into the render loop above: live mode updates each
  // aircraft's extrapolation (speed+heading) and starts a short correction blend from
  // wherever dead-reckoning currently thinks it is; scrub mode just sets up a new
  // two-point ease like before
  useEffect(() => {
    aircraftById.current = new Map(aircraft.map((a) => [a.icao24, a]));
    const now = performance.now();

    if (live) {
      const seen = new Set<string>();
      for (const a of aircraft) {
        if (a.latitude == null || a.longitude == null) continue;
        seen.add(a.icao24);
        const { vLon, vLat } = velocityToDegPerSec(a.latitude, a.velocity ?? 0, a.true_track ?? 0);
        const prevK = kinematics.current.get(a.icao24);
        if (prevK) {
          correction.current.set(a.icao24, { fromLon: prevK.lon, fromLat: prevK.lat, startedAt: now });
        }
        kinematics.current.set(a.icao24, { lon: a.longitude, lat: a.latitude, heading: a.true_track ?? 0, vLon, vLat });

        const hist = trailHistory.current.get(a.icao24) ?? [];
        hist.push([a.longitude, a.latitude]);
        if (hist.length > TRAIL_LENGTH) hist.shift();
        trailHistory.current.set(a.icao24, hist);
      }
      for (const id of [...kinematics.current.keys()]) {
        if (!seen.has(id)) {
          kinematics.current.delete(id);
          correction.current.delete(id);
        }
      }
    } else {
      const nextTarget = new Map<string, Pos>();
      for (const a of aircraft) {
        if (a.latitude == null || a.longitude == null) continue;
        nextTarget.set(a.icao24, { lon: a.longitude, lat: a.latitude, heading: a.true_track ?? 0 });

        const hist = trailHistory.current.get(a.icao24) ?? [];
        hist.push([a.longitude, a.latitude]);
        if (hist.length > TRAIL_LENGTH) hist.shift();
        trailHistory.current.set(a.icao24, hist);
      }
      scrubPrev.current = scrubTarget.current.size ? new Map(scrubTarget.current) : new Map(nextTarget);
      scrubTarget.current = nextTarget;
      scrubAnimStart.current = now;
    }
  }, [aircraft, live]);

  // update airport risk colors when predictions change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("airports") as maplibregl.GeoJSONSource | undefined;
    src?.setData(airportFeatures(predictions));
  }, [predictions]);

  // pull the airport filter chip's selection in: fly the camera there and open its
  // card, unless we're the one who just pushed this same code out (see click handler)
  useEffect(() => {
    if (selectedAirportProp === appliedAirportRef.current) return;
    appliedAirportRef.current = selectedAirportProp;
    const map = mapRef.current;
    if (selectedAirportProp) {
      setSelected({ kind: "airport", code: selectedAirportProp });
      const coords = AIRPORT_COORDS[selectedAirportProp];
      if (map && coords) {
        map.flyTo({ center: [coords[1], coords[0]], zoom: Math.max(map.getZoom(), 6), speed: 0.8 });
      }
    } else {
      setSelected((s) => (s?.kind === "airport" ? null : s));
    }
  }, [selectedAirportProp]);

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

  const selectedAircraft = selected?.kind === "aircraft" ? aircraftById.current.get(selected.id) : null;
  const { data: aircraftRisk } = useAircraftRisk(selected?.kind === "aircraft" ? selected.id : null);
  const selectedAirport =
    selected?.kind === "airport" ? predictions.find((p) => p.airport === selected.code) : null;

  const altitudeTrend =
    selected?.kind === "aircraft"
      ? history
          .map((snap) => snap.aircraft.find((a) => a.icao24 === selected.id)?.baro_altitude)
          .filter((v): v is number => v != null)
      : [];
  const speedTrend =
    selected?.kind === "aircraft"
      ? history
          .map((snap) => snap.aircraft.find((a) => a.icao24 === selected.id)?.velocity)
          .filter((v): v is number => v != null)
      : [];
  const riskTrend =
    selected?.kind === "airport"
      ? predictionsHistory
          .map((snap) => snap.predictions.find((p) => p.airport === selected.code)?.risk_score)
          .filter((v): v is number => v != null)
      : [];

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
          <div className="mt-2 border-t border-[var(--panel-border)] pt-2">
            <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-dim)]">altitude (m)</span>
            <Sparkline values={altitudeTrend} width={208} height={32} color="#60a5fa" />
            <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-dim)]">speed (m/s)</span>
            <Sparkline values={speedTrend} width={208} height={32} color="#a78bfa" />
          </div>

          {aircraftRisk && (
            <div className="mt-2 border-t border-[var(--panel-border)] pt-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-dim)]">
                  if departing {aircraftRisk.nearest_airport} now
                </span>
                <span className="font-num text-xs font-semibold" style={{ color: RISK_COLOR[aircraftRisk.risk_level] }}>
                  {Math.round(aircraftRisk.risk_score * 100)}%
                </span>
              </div>
              <dl className="mt-1.5 space-y-1 text-[11px]">
                <Row
                  label="type"
                  value={
                    aircraftRisk.aircraft_info.model
                      ? `${aircraftRisk.aircraft_info.model} (${aircraftRisk.aircraft_info.typecode})`
                      : (aircraftRisk.aircraft_info.typecode ?? "n/a")
                  }
                />
                {aircraftRisk.aircraft_info.operator && (
                  <Row label="operator" value={aircraftRisk.aircraft_info.operator} />
                )}
                {aircraftRisk.aircraft_info.registration && (
                  <Row label="registration" value={aircraftRisk.aircraft_info.registration} />
                )}
              </dl>
              {aircraftRisk.top_factors.length > 0 && (
                <ul className="mt-1.5 space-y-1">
                  {aircraftRisk.top_factors.map((f) => (
                    <li key={f.feature} className="flex items-start gap-1.5 text-[11px] text-[#d1d5db]">
                      <span className={f.direction === "increases" ? "text-[var(--risk-high)]" : "text-[var(--risk-low)]"}>
                        {f.direction === "increases" ? "▲" : "▼"}
                      </span>
                      <span>
                        {f.label} <span className="text-[var(--text-dim)]">({f.value})</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {selected?.kind === "airport" && (
        <div className="fade-in tick-corners absolute top-3 left-3 w-56 border border-[var(--panel-border-strong)] bg-[#0a0b0cf0] p-3 backdrop-blur-sm">
          <div className="flex items-start justify-between">
            <span className="font-num text-sm font-semibold text-white">{selected.code}</span>
            <button
              onClick={() => {
                appliedAirportRef.current = null;
                setSelected(null);
                onSelectAirportRef.current?.(null);
              }}
              className="text-[var(--text-dim)] hover:text-white"
            >
              ✕
            </button>
          </div>
          {selectedAirport ? (
            <>
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
                {selectedAirport.metar?.flight_category != null && (
                  <Row
                    label="flight cat."
                    value={
                      <span style={{ color: FLIGHT_CATEGORY_COLOR[selectedAirport.metar.flight_category] }}>
                        {selectedAirport.metar.flight_category_label}
                      </span>
                    }
                  />
                )}
                {selectedAirport.metar?.visibility_mi != null && (
                  <Row label="visibility" value={`${selectedAirport.metar.visibility_mi.toFixed(1)} mi`} />
                )}
                {selectedAirport.metar?.ceiling_ft != null && (
                  <Row
                    label="ceiling"
                    value={selectedAirport.metar.ceiling_ft >= 12_000 ? "unlimited" : `${Math.round(selectedAirport.metar.ceiling_ft)} ft`}
                  />
                )}
              </dl>
              {selectedAirport.top_factors.length > 0 && (
                <div className="mt-2 border-t border-[var(--panel-border)] pt-2">
                  <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-dim)]">why</span>
                  <ul className="mt-1 space-y-1">
                    {selectedAirport.top_factors.map((f) => (
                      <li key={f.feature} className="flex items-start gap-1.5 text-[11px] text-[#d1d5db]">
                        <span className={f.direction === "increases" ? "text-[var(--risk-high)]" : "text-[var(--risk-low)]"}>
                          {f.direction === "increases" ? "▲" : "▼"}
                        </span>
                        <span>
                          {f.label} <span className="text-[var(--text-dim)]">({f.value})</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="mt-2 text-[11px] text-[var(--text-dim)]">waiting for prediction...</p>
          )}
          <div className="mt-2 border-t border-[var(--panel-border)] pt-2">
            <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-dim)]">risk trend</span>
            <Sparkline
              values={riskTrend}
              width={208}
              height={32}
              color={selectedAirport ? RISK_COLOR[selectedAirport.risk_level] : "#9ca3af"}
            />
          </div>
        </div>
      )}

      <TimeSlider
        history={history}
        scrubIndex={scrubIndex}
        playing={playing}
        onScrub={onScrub}
        onTogglePlay={onTogglePlay}
        onGoLive={onGoLive}
        pollIntervalS={pollIntervalS}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-[var(--text-dim)]">{label}</dt>
      <dd className="font-num text-[#d1d5db]">{value}</dd>
    </div>
  );
}
