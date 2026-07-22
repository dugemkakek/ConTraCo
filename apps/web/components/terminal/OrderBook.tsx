"use client";

import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";

type Props = {
  symbol: string;
  depth?: number;
};

export function OrderBook({ symbol, depth = 10 }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["orderbook", symbol],
    queryFn: () => request<any>(`/api/v1/market-data/${symbol.replace("/", "-")}/orderbook?depth=${depth}`),
    refetchInterval: 10_000,
    enabled: !!symbol,
  });

  if (isLoading) return <div className="text-xs text-muted p-2">Loading depth…</div>;

  const asks = (data?.asks ?? []).slice(0, depth).reverse();
  const bids = (data?.bids ?? []).slice(0, depth);
  const maxVol = Math.max(
    ...asks.map((a: any) => parseFloat(a[1] ?? 0)),
    ...bids.map((b: any) => parseFloat(b[1] ?? 0)),
    1,
  );

  return (
    <div className="text-xs">
      <h4 className="text-[10px] text-muted uppercase font-semibold mb-1">{symbol} Depth</h4>
      {asks.length === 0 && bids.length === 0 ? (
        <p className="text-[10px] text-muted italic">No orderbook data available (mock provider)</p>
      ) : (
        <div className="flex flex-col gap-0.5">
          <div className="text-[9px] text-muted flex pb-1 border-b border-border">
            <span className="w-20">Price</span>
            <span className="w-16 text-right">Amount</span>
            <span className="flex-1" />
          </div>
          {asks.map((a: any, i: number) => (
            <div key={i} className="flex text-bearish relative">
              <span className="w-20 z-10">${parseFloat(a[0]).toFixed(2)}</span>
              <span className="w-16 text-right z-10">{parseFloat(a[1]).toFixed(4)}</span>
              <div
                className="absolute right-0 top-0 h-full bg-bearish/15"
                style={{ width: `${(parseFloat(a[1]) / maxVol) * 100}%` }}
              />
            </div>
          ))}
          <div className="border-t border-border my-1" />
          {bids.map((b: any, i: number) => (
            <div key={i} className="flex text-bullish relative">
              <span className="w-20 z-10">${parseFloat(b[0]).toFixed(2)}</span>
              <span className="w-16 text-right z-10">{parseFloat(b[1]).toFixed(4)}</span>
              <div
                className="absolute right-0 top-0 h-full bg-bullish/15"
                style={{ width: `${(parseFloat(b[1]) / maxVol) * 100}%` }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}