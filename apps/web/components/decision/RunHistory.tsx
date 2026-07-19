"use client";

import { useQuery } from "@tanstack/react-query";
import { analysisHistory } from "@/lib/api";

type Props = {
  symbol: string;
  onSelectRun: (runId: number) => void;
};

const STATE_COLOR: Record<string, string> = {
  LONG: "text-bullish",
  SHORT: "text-bearish",
  WAIT: "text-warning",
  AVOID: "text-bearish",
};

export function RunHistory({ symbol, onSelectRun }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["analysis-history", symbol],
    queryFn: () => analysisHistory(symbol, 10),
    refetchInterval: 30_000,
  });

  if (isLoading) return <p className="text-xs text-muted">Loading history…</p>;
  if (!data?.length) return <p className="text-xs text-muted">No past runs.</p>;

  return (
    <div className="flex flex-col gap-1">
      <h4 className="text-xs font-semibold text-muted uppercase mb-1">Recent Runs</h4>
      {data.map((r) => (
        <button
          key={r.id}
          onClick={() => onSelectRun(r.id)}
          className="flex items-center justify-between text-xs px-2 py-1 rounded hover:bg-border/40 text-left"
        >
          <div className="flex items-center gap-2">
            <span className="text-muted text-[10px]">
              {new Date(r.started_at).toLocaleTimeString()}
            </span>
            <span className={STATE_COLOR[r.final_state ?? ""] ?? "text-muted"}>
              {r.final_state ?? "—"}
            </span>
          </div>
          <span className="text-muted text-[10px]">{r.status}</span>
        </button>
      ))}
    </div>
  );
}
