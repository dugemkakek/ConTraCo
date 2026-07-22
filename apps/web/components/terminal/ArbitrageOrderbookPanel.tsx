"use client";

import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import { OrderBook } from "@/components/terminal/OrderBook";

/**
 * Panel 3 (Left-Bottom): Multi-Exchange Arbitrage & Orderbooks.
 * OrderBook is dynamic per symbol. Arbitrage spreads fetch from API.
 */
type Props = {
  symbol: string;
};

export function ArbitrageOrderbookPanel({ symbol }: Props) {
  // Fetch arbitrage yield data for the current symbol
  const { data: arbData } = useQuery({
    queryKey: ["arbitrage-yield", symbol],
    queryFn: () => request<{ opportunities: any[] }>("/api/v1/arbitrage/yield"),
    refetchInterval: 30_000,
    enabled: !!symbol,
  });

  const opps = arbData?.opportunities ?? [];
  // Filter opportunities matching the current symbol
  const symbolOpps = opps.filter((o: any) => o.symbol === symbol);
  const displayOpps = symbolOpps.length > 0 ? symbolOpps : opps.slice(0, 3);

  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <h4 className="text-[10px] text-muted uppercase font-semibold tracking-wider">
          Orderbook & Arbitrage
        </h4>
        <span className="text-[9px] text-muted font-mono">{symbol}</span>
      </div>
      <div className="flex-1 p-2 overflow-auto">
        <OrderBook symbol={symbol} depth={8} />
      </div>
      {/* Arbitrage Spreads */}
      <div className="border-t border-border px-3 py-2">
        <h4 className="text-[10px] text-muted uppercase font-semibold tracking-wider mb-1">
          Arbitrage Spreads
        </h4>
        {displayOpps.length > 0 ? (
          <div className="grid grid-cols-4 gap-2 text-[9px] font-mono text-muted">
            <span>Venue</span><span>Spot</span><span>Perp</span><span>Spread</span>
            {displayOpps.map((o: any, i: number) => (
              <div key={i} className="contents">
                <span className="text-primary">{o.short_venue}</span>
                <span className="text-primary">${o.spot_price?.toFixed(2)}</span>
                <span className="text-primary">${o.perp_price?.toFixed(2)}</span>
                <span className={o.net_apy > 0 ? "text-bullish" : "text-bearish"}>
                  {o.net_apy > 0 ? "+" : ""}{o.net_apy?.toFixed(2)}% APY
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[9px] text-muted italic">No live arbitrage data available</p>
        )}
      </div>
    </div>
  );
}