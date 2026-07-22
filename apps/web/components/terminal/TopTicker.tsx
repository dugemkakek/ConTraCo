"use client";

import { useQuery } from "@tanstack/react-query";
import { getMarketOverview } from "@/lib/api";

/**
 * Neo-Bloomberg Macro Ticker — sits at the very top of the terminal.
 * Shows BTC Dominance, Fear & Greed, Gas, and 24h Volume.
 * Data is currently mocked; will be wired to a real endpoint in Phase 14.
 */
export function TopTicker() {
  const { data: overview } = useQuery({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 30_000,
  });

  const btc = overview?.tickers?.find((t) => t.symbol === "BTC/USDT");
  const btcPrice = btc?.last?.toLocaleString(undefined, { minimumFractionDigits: 2 });
  const btcChange = btc?.change_24h_pct;

  return (
    <div className="h-8 bg-panel border-b border-border flex items-center px-3 gap-5 text-xs font-mono select-none">
      {/* BTC Price */}
      <span className="text-primary font-semibold">
        BTC <span className="text-muted">${btcPrice ?? "—"}</span>
        {btcChange != null && (
          <span className={btcChange >= 0 ? "text-bullish ml-1" : "text-bearish ml-1"}>
            {btcChange >= 0 ? "+" : ""}{btcChange.toFixed(2)}%
          </span>
        )}
      </span>

      {overview?.tickers.slice(1, 4).map((ticker) => (
        <span key={ticker.symbol} className="contents">
          <span className="text-border">/</span>
          <span className="text-muted">
            {ticker.symbol.split("/")[0]} <span className="text-primary">${ticker.last.toLocaleString()}</span>
            {ticker.change_24h_pct != null && (
              <span className={ticker.change_24h_pct >= 0 ? "text-bullish ml-1" : "text-bearish ml-1"}>
                {ticker.change_24h_pct >= 0 ? "+" : ""}{ticker.change_24h_pct.toFixed(2)}%
              </span>
            )}
          </span>
        </span>
      ))}

      <span className="text-border">|</span>

      {/* Status */}
      <span className="ml-auto flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-bullish status-pulse" />
        <span className="text-muted">{overview?.provider?.toUpperCase() ?? "CONNECTING"}</span>
      </span>
    </div>
  );
}