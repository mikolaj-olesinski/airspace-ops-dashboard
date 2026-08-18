import { useFeatureImportance } from "../lib/api";
import EmptyState from "./EmptyState";

export default function FeatureImportanceChart() {
  const { data, loading, error } = useFeatureImportance();
  const features = data?.features ?? [];

  if (loading && features.length === 0) {
    return <EmptyState message="loading model..." variant="loading" />;
  }
  if (error && features.length === 0) {
    return <EmptyState message={`unavailable: ${error}`} variant="error" />;
  }

  const max = Math.max(...features.map((f) => f.importance), 0.0001);

  return (
    <div className="flex h-full flex-col justify-center gap-[6px] overflow-y-auto">
      {features.map((f, i) => (
        <div key={f.feature} className="fade-in flex items-center gap-2" style={{ animationDelay: `${i * 30}ms` }}>
          <span className="w-24 shrink-0 truncate font-num text-[10px] text-[var(--text-mid)]" title={f.feature}>
            {f.feature}
          </span>
          <div className="h-[5px] flex-1 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full rounded-full bg-[#a78bfa]"
              style={{ width: `${(f.importance / max) * 100}%`, transition: "width 0.7s ease-out" }}
            />
          </div>
          <span className="w-9 shrink-0 text-right font-num text-[10px] text-[var(--text-mid)]">
            {Math.round(f.importance * 100)}%
          </span>
        </div>
      ))}
    </div>
  );
}
