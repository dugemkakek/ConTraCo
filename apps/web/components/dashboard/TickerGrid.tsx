import Link from "next/link";
import type { TickerSnapshot } from "@/lib/api";
import { Sparkline } from "./Sparkline";

type Props = {
  tickers: TickerSnapshot[];
};

function TrendArrow({ trend }: { trend: string }) {
  if (trend === "up") return <span className="text-bullish text-xs">▲</span>;
  if (trend === "down") return <span className="text-bearish text-xs">▼</span>;
  return <span className="text-neutral text-xs">—</span>;
}

function RsiPill({ rsi }: { rsi: number | null }) {
  if (rsi === null) return null;
  const color =
    rsi >= 70
      ? "bg-bearish/20 text-bearish border-bearish/40"
      : rsi <= 30
        ? "bg-bullish/20 text-bullish border-bullish/40"
        : "bg-neutral/20 text-muted border-border";
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded-full border ${color}`}
    >
      {rsi >= 70 ? "OB" : rsi <= 30 ? "OS" : "—"}
    </span>
  );
}

export function TickerGrid({ tickers }: Props) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
      {tickers.map((t) => (
        <Link
          key={t.symbol}
          href={`/terminal/${t.symbol.replace("/", "-")}`}
          className="bg-panel border border-border rounded-md p-3 flex flex-col gap-2 hover:border-info/50 transition-colors"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">
              {t.symbol.replace("/USDT", "")}
            </span>
            <TrendArrow trend={t.trend} />
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold">
              ${t.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span
              className={`text-xs font-medium ${
                t.change_24h_pct !== null && t.change_24h_pct >= 0
                  ? "text-bullish"
                  : "text-bearish"
              }`}
            >
              {t.change_24h_pct !== null
                ? `${t.change_24h_pct >= 0 ? "+" : ""}${t.change_24h_pct.toFixed(1)}%`
                : "—"}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <Sparkline data={t.sparkline} />
            <RsiPill rsi={t.rsi_14} />
          </div>
        </Link>
      ))}
    </div>
  );
}
