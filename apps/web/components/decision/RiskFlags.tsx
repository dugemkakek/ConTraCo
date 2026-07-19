import type { RunOut } from "@/lib/api";

export function RiskFlags({ run }: { run: RunOut }) {
  const allFlags = run.opinions?.flatMap((o) => o.risk_flags ?? []) ?? [];
  const uniqueFlags = [...new Set(allFlags)];

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-muted uppercase">Risk Flags</h4>
      {uniqueFlags.length === 0 ? (
        <span className="text-bullish text-xs">✓ No risk flags</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {uniqueFlags.map((flag) => (
            <span
              key={flag}
              className="text-[10px] px-1.5 py-0.5 rounded bg-bearish/20 text-bearish border border-bearish/40"
            >
              {flag}
            </span>
          ))}
        </div>
      )}
      {run.decision?.vetoes?.length ? (
        <>
          <h4 className="text-xs font-semibold text-bearish uppercase mt-1">Vetoes</h4>
          {run.decision.vetoes.map((v: string, i: number) => (
            <span key={i} className="text-[10px] text-bearish">
              {v} ({run.decision?.veto_sources?.[i] ?? "unknown"})
            </span>
          ))}
        </>
      ) : null}
    </div>
  );
}
