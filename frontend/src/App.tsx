import Header from "./components/Header";
import Panel from "./components/Panel";
import MapView from "./components/MapView";
import StatGauge from "./components/StatGauge";
import RiskBars from "./components/RiskBars";
import RiskRadar from "./components/RiskRadar";
import BriefingPanel from "./components/BriefingPanel";
import { useLiveStates, usePredictions } from "./lib/api";

export default function App() {
  const { data: liveStates, error: liveError } = useLiveStates();
  const { data: predictions } = usePredictions();

  const aircraft = liveStates?.aircraft ?? [];
  const preds = predictions?.predictions ?? [];
  const topRisk = [...preds].sort((a, b) => b.risk_score - a.risk_score)[0];

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
          <Panel label="Live Traffic" sublabel={`${aircraft.length} aircraft`} bodyClassName="!p-0" className="h-full overflow-hidden">
            <MapView aircraft={aircraft} predictions={preds} />
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
            <BriefingPanel predictions={preds} />
          </Panel>
        </div>
      </main>
    </div>
  );
}
