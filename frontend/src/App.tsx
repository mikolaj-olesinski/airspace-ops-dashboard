import { useEffect, useMemo, useRef, useState } from "react";
import Header from "./components/Header";
import Panel from "./components/Panel";
import MapView from "./components/MapView";
import StatGauge from "./components/StatGauge";
import RiskBars from "./components/RiskBars";
import RiskRadar from "./components/RiskRadar";
import BriefingPanel from "./components/BriefingPanel";
import AreaChart from "./components/AreaChart";
import FeatureImportanceChart from "./components/FeatureImportanceChart";
import AirportFilter from "./components/AirportFilter";
import LiveDeltas from "./components/LiveDeltas";
import { useLiveStates, usePredictions, usePredictionsHistory } from "./lib/api";
import { useAircraftHistory, type Snapshot } from "./lib/history";
import { AIRPORT_COORDS } from "./lib/airports";

// matches backend/opensky_client.py's count_aircraft_near default -- keeps the
// per-airport "aircraft near X" figures consistent between frontend and backend
const AIRPORT_RADIUS_DEG = 0.5;

const PLAYBACK_STEP_MS = 450;
// matches backend/live_state_cache.py's POLL_INTERVAL_S -- shown as a countdown so the
// ~90s cadence (forced by OpenSky's free-tier credit budget, see that module's
// docstring) reads as "next update in Xs" instead of looking stuck
const LIVE_POLL_INTERVAL_S = 90;

export default function App() {
  const { data: liveStates, error: liveError } = useLiveStates();
  const { data: predictions } = usePredictions();
  const { data: predictionsHistoryData } = usePredictionsHistory();

  const aircraft = liveStates?.aircraft ?? [];
  const preds = predictions?.predictions ?? [];
  const predictionsHistory = predictionsHistoryData?.snapshots ?? [];
  const topRisk = [...preds].sort((a, b) => b.risk_score - a.risk_score)[0];

  // rolling in-browser buffer of live snapshots, for the time-slider/playback --
  // there's no server-side history (OpenSky's free tier is live-only), so this only
  // covers time since the page was opened
  const latestSnapshot: Snapshot | null = useMemo(
    () => (liveStates ? { time: liveStates.time, aircraft: liveStates.aircraft } : null),
    [liveStates],
  );
  const history = useAircraftHistory(latestSnapshot);

  const [scrubIndex, setScrubIndex] = useState<number | null>(null); // null == live
  const [playing, setPlaying] = useState(false);
  const [selectedAirport, setSelectedAirport] = useState<string | null>(null);
  const historyLenRef = useRef(0);
  historyLenRef.current = history.length;

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setScrubIndex((idx) => {
        const maxIdx = historyLenRef.current - 1;
        const current = idx ?? maxIdx;
        const next = current + 1;
        if (next >= maxIdx) {
          setPlaying(false);
          return null; // reached live -- snap back and stop
        }
        return next;
      });
    }, PLAYBACK_STEP_MS);
    return () => clearInterval(id);
  }, [playing]);

  function handleScrub(index: number) {
    setPlaying(false);
    setScrubIndex(index);
  }
  function handleTogglePlay() {
    setPlaying((p) => {
      if (!p && scrubIndex === null) setScrubIndex(0); // replay from the start of the buffer
      return !p;
    });
  }
  function handleGoLive() {
    setPlaying(false);
    setScrubIndex(null);
  }

  const displayedAircraft = scrubIndex !== null && history[scrubIndex] ? history[scrubIndex].aircraft : aircraft;
  const isScrubbing = scrubIndex !== null;

  // Airspace Load series: total aircraft in the whole tracked bbox by default, or --
  // when an airport is filtered -- just the aircraft within radar range of it, recomputed
  // client-side from the same snapshots (no extra backend call needed)
  const loadValues = useMemo(() => {
    if (!selectedAirport) return history.map((s) => s.aircraft.length);
    const [lat, lon] = AIRPORT_COORDS[selectedAirport];
    return history.map(
      (s) =>
        s.aircraft.filter(
          (a) =>
            a.latitude != null &&
            a.longitude != null &&
            Math.abs(a.latitude - lat) <= AIRPORT_RADIUS_DEG &&
            Math.abs(a.longitude - lon) <= AIRPORT_RADIUS_DEG,
        ).length,
    );
  }, [history, selectedAirport]);

  const focusRisk = selectedAirport ? preds.find((p) => p.airport === selectedAirport) : topRisk;
  const trackedCount = selectedAirport ? (loadValues[loadValues.length - 1] ?? 0) : aircraft.length;

  return (
    <div className="flex h-full flex-col">
      <Header isLive={!liveError && !!liveStates} />
      <AirportFilter selected={selectedAirport} onSelect={setSelectedAirport} predictions={preds} />
      <LiveDeltas history={predictionsHistory} />

      <main
        className="grid flex-1 gap-3 overflow-y-auto p-3"
        style={{
          gridTemplateColumns: "2fr 1fr 1fr",
          gridTemplateRows: "200px 1fr 150px 170px",
          gridTemplateAreas: `"map gauge1 gauge2" "map bars radar" "load load importance" "briefing briefing briefing"`,
        }}
      >
        <div style={{ gridArea: "map" }} className="min-h-0">
          <Panel
            label="Live Traffic"
            sublabel={`${aircraft.length} aircraft · click to inspect`}
            bodyClassName="!p-0"
            className="h-full overflow-hidden"
          >
            <MapView
              aircraft={displayedAircraft}
              predictions={preds}
              live={!isScrubbing}
              transitionMs={PLAYBACK_STEP_MS}
              history={history}
              predictionsHistory={predictionsHistory}
              scrubIndex={scrubIndex}
              playing={playing}
              onScrub={handleScrub}
              onTogglePlay={handleTogglePlay}
              onGoLive={handleGoLive}
              selectedAirport={selectedAirport}
              onSelectAirport={setSelectedAirport}
              pollIntervalS={LIVE_POLL_INTERVAL_S}
            />
          </Panel>
        </div>

        <div style={{ gridArea: "gauge1" }} className="min-h-0">
          <Panel label="Aircraft Tracked" sublabel={selectedAirport ? `near ${selectedAirport}` : undefined} className="h-full">
            <StatGauge
              value={trackedCount}
              max={Math.max(selectedAirport ? 60 : 300, trackedCount)}
              format={(v) => String(Math.round(v))}
              label={selectedAirport ? `near ${selectedAirport}` : "in region"}
            />
          </Panel>
        </div>

        <div style={{ gridArea: "gauge2" }} className="min-h-0">
          <Panel label={selectedAirport ? "Airport Risk" : "Peak Risk"} className="h-full">
            <StatGauge
              value={focusRisk?.risk_score ?? 0}
              max={1}
              format={(v) => (focusRisk ? `${Math.round(v * 100)}%` : "--")}
              label={focusRisk?.airport ?? "n/a"}
              color={
                focusRisk?.risk_level === "high"
                  ? "var(--risk-high)"
                  : focusRisk?.risk_level === "medium"
                    ? "var(--risk-medium)"
                    : "var(--risk-low)"
              }
            />
          </Panel>
        </div>

        <div style={{ gridArea: "bars" }} className="min-h-0">
          <Panel label="Delay Risk / Airport" className="h-full">
            <RiskBars predictions={preds} history={predictionsHistory} selectedAirport={selectedAirport} onSelect={setSelectedAirport} />
          </Panel>
        </div>

        <div style={{ gridArea: "radar" }} className="min-h-0">
          <Panel label="Risk Profile" className="h-full" bodyClassName="flex items-center">
            <RiskRadar predictions={preds} selectedAirport={selectedAirport} onSelect={setSelectedAirport} />
          </Panel>
        </div>

        <div style={{ gridArea: "load" }} className="min-h-0">
          <Panel
            label="Airspace Load"
            sublabel={selectedAirport ? `aircraft near ${selectedAirport} over time` : "aircraft tracked over time"}
            className="h-full"
          >
            <AreaChart values={loadValues} timestamps={history.map((s) => s.time)} color="#e5e7eb" unit="aircraft" />
          </Panel>
        </div>

        <div style={{ gridArea: "importance" }} className="min-h-0">
          <Panel label="Feature Importance" sublabel="LightGBM · gain" className="h-full">
            <FeatureImportanceChart />
          </Panel>
        </div>

        <div style={{ gridArea: "briefing" }} className="min-h-0">
          <Panel label={selectedAirport ? `${selectedAirport} Briefing` : "Ops Briefing"} className="h-full">
            <BriefingPanel selectedAirport={selectedAirport} />
          </Panel>
        </div>
      </main>
    </div>
  );
}
