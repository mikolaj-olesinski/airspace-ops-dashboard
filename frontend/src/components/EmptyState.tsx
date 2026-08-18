interface EmptyStateProps {
  message: string;
  variant?: "loading" | "waiting" | "error";
}

/** Consistent placeholder for panels that have nothing to show yet, instead of each
 * one improvising its own plain text. */
export default function EmptyState({ message, variant = "waiting" }: EmptyStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
      {variant === "loading" ? (
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-[var(--text-dim)]"
              style={{ animation: "pulse-dot 1.2s ease-in-out infinite", animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      ) : (
        <span
          className={`h-1.5 w-1.5 rounded-full ${variant === "error" ? "bg-[var(--risk-high)]" : "bg-[var(--text-dim)]"}`}
        />
      )}
      <span className="max-w-[80%] text-[11px] text-[var(--text-dim)]">{message}</span>
    </div>
  );
}
