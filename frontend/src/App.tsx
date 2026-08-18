import { useEffect, useMemo, useRef, useState } from "react";
import Header from "./components/Header";
import Panel from "./components/Panel";
import MapView from "./components/MapView";
import StatGauge from "./components/StatGauge";
import RiskBars from "./components/RiskBars";
import RiskRadar from "./components/RiskRadar";
import BriefingPanel from "./components/BriefingPanel";
import { useLiveStates, usePredictions } from "./lib/api";
import { useAircraftHistory, type Snapshot } from "./lib/history";

const PLAYBACK_STEP_MS = 450;
const LIVE_TRANSITION_MS = 11_000;

export default function App() {
  const { data: liveStates, error: liveError } = useLiveStates();
  const { data: predictions } = usePredictions();

  const aircraft = liveStates?.aircraft ?? [];
  const preds = predictions?.predictions ?? [];
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

  return (
    <div className="flex h-full flex-col">
      <Header isLive={!liveError && !!liveStates} />

      <main
        className="grid flex-1 gap-3 p-3"
        style={{
          gridTemplateColumns: "2fr 1fr 1fr",
          gridTemplateRows: "200px 1fr 170px",
          gridTemplateAreas: `"map gauge1 gauge2" "map bars radar" "briefing briefing briefing"`,
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
              transitionMs={isScrubbing ? PLAYBACK_STEP_MS : LIVE_TRANSITION_MS}
              history={history}
              scrubIndex={scrubIndex}
              playing={playing}
              onScrub={handleScrub}
              onTogglePlay={handleTogglePlay}
              onGoLive={handleGoLive}
            />
          </Panel>
        </div>

        <div style={{ gridArea: "gauge1" }} className="min-h-0">
          <Panel label="Aircraft Tracked" className="h-full">
            <StatGauge
              value={aircraft.length}
              max={Math.max(300, aircraft.length)}
              displayValue={String(aircraft.length)}
              label="in region"
            />
          </Panel>
        </div>

        <div style={{ gridArea: "gauge2" }} className="min-h-0">
          <Panel label="Peak Risk" className="h-full">
            <StatGauge
              value={topRisk?.risk_score ?? 0}
              max={1}
              displayValue={topRisk ? `${Math.round(topRisk.risk_score * 100)}%` : "--"}
              label={topRisk?.airport ?? "n/a"}
              color={
                topRisk?.risk_level === "high"
                  ? "var(--risk-high)"
                  : topRisk?.risk_level === "medium"
                    ? "var(--risk-medium)"
                    : "var(--risk-low)"
              }
            />
          </Panel>
        </div>

        <div style={{ gridArea: "bars" }} className="min-h-0">
          <Panel label="Delay Risk / Airport" className="h-full">
            <RiskBars predictions={preds} />
          </Panel>
        </div>

        <div style={{ gridArea: "radar" }} className="min-h-0">
          <Panel label="Risk Profile" className="h-full" bodyClassName="flex items-center">
            <RiskRadar predictions={preds} />
          </Panel>
        </div>

        <div style={{ gridArea: "briefing" }} className="min-h-0">
          <Panel label="Ops Briefing" className="h-full">
            <BriefingPanel />
          </Panel>
        </div>
      </main>
    </div>
  );
}
