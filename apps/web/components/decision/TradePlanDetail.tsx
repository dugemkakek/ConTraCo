import type { RunOut } from "@/lib/api";

export function TradePlanDetail({ run }: { run: RunOut }) {
  const tp = run.trade_plan;
  if (!tp) return null;

  const row = (label: string, value: string | number | null | undefined, className = "") => (
    <div className="flex justify-between text-xs py-0.5">
      <span className="text-muted">{label}</span>
      <span className={`text-primary font-medium ${className}`}>
        {value ?? "—"}
      </span>
    </div>
  );

  const color = tp.direction === "LONG" ? "text-bullish" : tp.direction === "SHORT" ? "text-bearish" : "";

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-muted uppercase">Trade Plan</h4>
      <div className="flex flex-col border border-border rounded-md p-2">
        {row("Direction", tp.direction, color + " font-semibold")}
        {row("Entry", tp.entry_price ? `$${tp.entry_price.toFixed(2)}` : null)}
        {row("Stop", tp.stop_price ? `$${tp.stop_price.toFixed(2)}` : null, "text-bearish")}
        {row("Take Profit", tp.take_profit ? `$${tp.take_profit.toFixed(2)}` : null, "text-bullish")}
        {row("R:R", tp.risk_reward?.toFixed(2) ?? null)}
        {row("Max Position", tp.position_size_pct ? `${(tp.position_size_pct * 100).toFixed(1)}%` : null)}
      </div>
      {tp.invalidation && (
        <div className="text-xs text-warning">
          <span className="font-semibold">Invalidation:</span> {tp.invalidation}
        </div>
      )}
      {tp.risk_review && (
        <div className="text-xs text-muted">
          <span className="font-semibold">Risk:</span> {tp.risk_review}
        </div>
      )}
      {tp.synthesis && (
        <div className="text-xs text-primary/80">
          <span className="font-semibold">Synthesis:</span> {tp.synthesis}
        </div>
      )}
    </div>
  );
}
