"use client";

import { DebateChamber } from "@/components/decision/DebateChamber";
import type { RunOut } from "@/lib/api";

/**
 * Panel 4 (Right-Bottom): Debate Chamber & RSS News Feed.
 * Phase 11: Live debate chamber from council opinions.
 * Phase 14: Will wire real RSS feed from /api/v1/fundamentals/news.
 */
type Props = {
  symbol: string;
  run: RunOut | null;
};

export function DebateNewsPanel({ symbol, run }: Props) {
  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <h4 className="text-[10px] text-muted uppercase font-semibold tracking-wider font-mono">
          CRO / Debate Chamber
        </h4>
        <span className="text-[9px] text-info font-mono">EXPLAINABILITY LIVE</span>
      </div>

      {/* Debate Chamber */}
      <div className="flex-1 overflow-auto">
        {run?.opinions?.length ? (
          <DebateChamber opinions={run.opinions} decision={run.decision} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-xs text-muted gap-2 p-4">
            <p>Run analysis to see the agent debate</p>
          </div>
        )}
      </div>

      <div className="border-t border-border px-3 py-2 shrink-0 flex items-center justify-between font-mono text-[9px]">
        <span className="text-muted">SYMBOL CONTEXT</span>
        <span className="text-primary">{symbol}</span>
      </div>
    </div>
  );
}