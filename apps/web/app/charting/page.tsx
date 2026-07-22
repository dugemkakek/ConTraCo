"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Droplets, Flame, BookOpen, LayoutGrid, Square } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  getFundingOI,
  getLiquidityHeatmap,
  type FundingOI,
  type LiquidityHeatmap,
} from "@/lib/api";
import { TradingViewChart } from "@/components/chart/TradingViewChart";
import { MultiChartGrid } from "@/components/chart/MultiChartGrid";
import { SymbolSearch } from "@/components/terminal/SymbolSearch";
import { VenueSelector } from "@/components/terminal/VenueSelector";
import { TimeframeSelector } from "@/components/terminal/TimeframeSelector";
import { OrderBook } from "@/components/terminal/OrderBook";

function LiquidityPanel({ symbol }: { symbol: string }) {
  const { data } = useQuery({
    queryKey: ["liquidity-heatmap", symbol],
    queryFn: () => getLiquidityHeatmap(symbol),
    refetchInterval: 60_000,
  });

  const levels = data?.levels ?? [];
  const maxVol = Math.max(...levels.map((l) => l.volume_usd), 1);

  return (
    <section className="border border-border bg-panel">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Droplets className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Liquidation Heatmap</span>
        {data?.source === "mock" && (
          <span className="ml-auto text-[8px] font-mono text-muted">SIM</span>
        )}
      </header>
      <div className="p-2 flex flex-col gap-1.5">
        {levels.length === 0 && (
          <p className="text-[10px] text-muted italic px-1 py-2">No cluster data</p>
        )}
        {levels
          .slice()
          .sort((a, b) => b.price - a.price)
          .map((l, i) => {
            const isShort = l.type === "short_liquidation";
            return (
              <div key={i} className="group relative">
                <div className="flex items-center justify-between text-[9px] font-mono px-1 mb-0.5">
                  <span className={isShort ? "text-bullish" : "text-bearish"}>
                    ${l.price.toLocaleString()}
                  </span>
                  <span className="text-muted">
                    {(l.volume_usd / 1e6).toFixed(0)}M · {Math.round(l.intensity * 100)}%
                  </span>
                </div>
                <div className="h-2 bg-bg overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 group-hover:brightness-150 ${
                      isShort ? "bg-bullish/60" : "bg-bearish/60"
                    }`}
                    style={{ width: `${(l.volume_usd / maxVol) * 100}%` }}
                  />
                </div>
              </div>
            );
          })}
        <p className="text-[8px] font-mono text-muted px-1 pt-1">
          <span className="text-bullish">■</span> SHORT LIQ ABOVE ·{" "}
          <span className="text-bearish">■</span> LONG LIQ BELOW
        </p>
      </div>
    </section>
  );
}

function FundingOIPanel({ symbol }: { symbol: string }) {
  const { data } = useQuery({
    queryKey: ["funding-oi", symbol],
    queryFn: () => getFundingOI(symbol),
    refetchInterval: 60_000,
  });

  const f = data?.funding;
  const oi = data?.open_interest;

  return (
    <section className="border border-border bg-panel">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Flame className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Funding / Open Interest</span>
      </header>
      <div className="grid grid-cols-2 gap-px bg-border">
        <Cell label="FUNDING NOW" value={f ? `${(f.current * 100).toFixed(4)}%` : "—"} tone={f && f.current >= 0 ? "bull" : "bear"} />
        <Cell label="PREDICTED" value={f ? `${(f.predicted * 100).toFixed(4)}%` : "—"} tone={f && f.predicted >= 0 ? "bull" : "bear"} />
        <Cell label="ANNUALIZED" value={f ? `${f.annualized.toFixed(1)}%` : "—"} tone={f && f.annualized >= 0 ? "bull" : "bear"} />
        <Cell label="TREND" value={f?.trend?.toUpperCase() ?? "—"} />
        <Cell label="OI" value={oi ? `$${(oi.current / 1e9).toFixed(2)}B` : "—"} />
        <Cell label="OI 24H" value={oi ? `${oi.change_24h_pct >= 0 ? "+" : ""}${oi.change_24h_pct.toFixed(1)}%` : "—"} tone={oi && oi.change_24h_pct >= 0 ? "bull" : "bear"} />
        <Cell label="L/S RATIO" value={oi ? oi.long_short_ratio.toFixed(2) : "—"} tone={oi && oi.long_short_ratio >= 1 ? "bull" : "bear"} />
        <Cell label="SOURCE" value={data?.source?.toUpperCase() ?? "—"} />
      </div>
    </section>
  );
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: "bull" | "bear" }) {
  return (
    <div className="bg-panel px-3 py-2">
      <div className="terminal-label mb-1">{label}</div>
      <div
        className={`font-mono text-xs font-semibold ${
          tone === "bull" ? "text-bullish" : tone === "bear" ? "text-bearish" : "text-primary"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export default function ChartingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [venue, setVenue] = useState("binance");
  const [timeframe, setTimeframe] = useState("1h");
  const [view, setView] = useState<"single" | "grid">("single");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      {/* Control bar */}
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <span className="terminal-label mr-1">Charting & Liquidity</span>
        {view === "single" && (
          <>
            <SymbolSearch onSelect={(sym) => setSymbol(sym)} />
            <VenueSelector value={venue} onChange={setVenue} />
            <TimeframeSelector value={timeframe} onChange={setTimeframe} />
            <span className="ml-auto font-mono text-[9px] text-muted">
              {symbol} · {venue.toUpperCase()} · {timeframe.toUpperCase()}
            </span>
          </>
        )}
        <div className={`flex items-center gap-1 ${view === "single" ? "" : "ml-auto"}`}>
          <button
            onClick={() => setView("single")}
            className={`h-6 w-6 flex items-center justify-center border transition-colors ${
              view === "single"
                ? "border-info text-info bg-info/10"
                : "border-border text-muted hover:text-primary"
            }`}
            title="Single chart + panels"
          >
            <Square className="w-3 h-3" />
          </button>
          <button
            onClick={() => setView("grid")}
            className={`h-6 w-6 flex items-center justify-center border transition-colors ${
              view === "grid"
                ? "border-info text-info bg-info/10"
                : "border-border text-muted hover:text-primary"
            }`}
            title="Multi-ticker grid"
          >
            <LayoutGrid className="w-3 h-3" />
          </button>
        </div>
      </header>

      {view === "grid" ? (
        <div className="flex-1 min-h-0">
          <MultiChartGrid />
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex">
          {/* Chart — 72% */}
          <div className="flex-[72] min-w-0 relative">
            <TradingViewChart symbol={symbol} venue={venue} interval={timeframe} />
          </div>

          {/* Right rail — 28% */}
          <aside className="flex-[28] min-w-[280px] border-l border-border overflow-y-auto flex flex-col gap-2 p-2 bg-bg">
            <LiquidityPanel symbol={symbol} />
            <FundingOIPanel symbol={symbol} />
            <section className="border border-border bg-panel p-2">
              <header className="flex items-center gap-2 mb-1">
                <BookOpen className="w-3.5 h-3.5 text-info" />
                <span className="terminal-label">Orderbook</span>
              </header>
              <OrderBook symbol={symbol} depth={8} />
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
