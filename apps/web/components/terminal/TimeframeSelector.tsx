"use client";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

export function TimeframeSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (tf: string) => void;
}) {
  return (
    <div className="flex gap-1">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf}
          onClick={() => onChange(tf)}
          data-testid={`timeframe-${tf}`}
          className={`px-2 py-1 text-xs rounded-md border transition ${
            value === tf
              ? "bg-info/20 border-info text-info"
              : "border-border text-muted hover:text-primary"
          }`}
        >
          {tf}
        </button>
      ))}
    </div>
  );
}
