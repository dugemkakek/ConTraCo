import type { MarketOverview } from "@/lib/api";

/**
 * Derives a single market-condition verdict from breadth + BTC trend + BTC RSI.
 *
 * score  = (up - down) / total           → -1..1
 *        + BTC-trend nudge               → ±0.5
 *        + contrarian RSI nudge          → ±0.5 (overbought = risk-off, oversold = risk-on)
 */
function computeVerdict(o: MarketOverview): {
  label: "RISK-ON" | "RISK-OFF" | "MIXED";
  color: string;
  caption: string;
} {
  const b = o.breadth;
  const total = b.up + b.down + b.flat || 1;
  let score = (b.up - b.down) / total;

  const btc = o.tickers.find((t) => t.symbol === "BTC/USDT");
  if (btc) {
    score += btc.trend === "up" ? 0.5 : btc.trend === "down" ? -0.5 : 0;
    if (btc.rsi_14 !== null) {
      score += btc.rsi_14 >= 70 ? -0.5 : btc.rsi_14 <= 30 ? 0.5 : 0;
    }
  }

  let label: "RISK-ON" | "RISK-OFF" | "MIXED";
  if (score > 0.5) label = "RISK-ON";
  else if (score < -0.5) label = "RISK-OFF";
  else label = "MIXED";
  const color =
    label === "RISK-ON" ? "text-bullish" : label === "RISK-OFF" ? "text-bearish" : "text-warning";

  // Table-driven caption — no if-ladder
  const captions: Record<string, string> = {
    "RISK-ON": "Most tracked majors are above their short-term averages.",
    "RISK-OFF": "Breadth is negative; caution warranted on new entries.",
    "MIXED": "Mixed signals across the board — selective entries only.",
  };

  return { label, color, caption: captions[label] ?? "" };
}

type Props = { overview: MarketOverview };

export function MarketConditionCard({ overview }: Props) {
  const verdict = computeVerdict(overview);
  const btc = overview.tickers.find((t) => t.symbol === "BTC/USDT");

  return (
    <div className="bg-panel border border-border rounded-md p-4 flex flex-col gap-2">
      <span className="text-xs text-muted uppercase tracking-wider">Market Condition</span>
      <span className={`text-2xl font-bold ${verdict.color}`}>{verdict.label}</span>
      <p className="text-xs text-muted">
        {btc && `BTC ${btc.trend} · RSI ${btc.rsi_14 ?? "—"}`}
        {btc && " · "}
        breadth {overview.breadth.up}↑ {overview.breadth.down}↓ {overview.breadth.flat}→
      </p>
      <p className="text-xs text-primary/70">{verdict.caption}</p>
    </div>
  );
}
