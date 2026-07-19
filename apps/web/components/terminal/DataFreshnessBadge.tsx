export function DataFreshnessBadge({
  freshness,
  latestTimestamp,
}: {
  freshness: "FRESH" | "STALE" | "UNKNOWN";
  latestTimestamp: string | null;
}) {
  const colorMap: Record<string, string> = {
    FRESH: "bg-bullish/20 border-bullish text-bullish",
    STALE: "bg-warning/20 border-warning text-warning",
    UNKNOWN: "bg-neutral/20 border-neutral text-neutral",
  };

  return (
    <div
      data-testid="data-freshness-badge"
      className={`flex items-center gap-2 px-2 py-1 rounded-md border text-xs ${colorMap[freshness]}`}
    >
      <span className="font-medium">{freshness}</span>
      {latestTimestamp && (
        <span className="text-muted">
          {new Date(latestTimestamp).toLocaleString()}
        </span>
      )}
    </div>
  );
}
