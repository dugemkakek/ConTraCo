"use client";

import { useEffect, useState, useCallback } from "react";
import { Activity, Command, Crosshair, Focus, ScanLine } from "lucide-react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useAuth } from "@/lib/auth-context";
import { getMarketOverview, runAnalysis, type RunOut } from "@/lib/api";
import { TradingViewChart } from "@/components/chart/TradingViewChart";
import { TimeframeSelector } from "@/components/terminal/TimeframeSelector";
import { SymbolSearch } from "@/components/terminal/SymbolSearch";
import { VenueSelector } from "@/components/terminal/VenueSelector";
import { TopTicker } from "@/components/terminal/TopTicker";
import { AgentCouncilPanel } from "@/components/decision/AgentCouncilPanel";
import { ArbitrageOrderbookPanel } from "@/components/terminal/ArbitrageOrderbookPanel";
import { DebateNewsPanel } from "@/components/terminal/DebateNewsPanel";

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [symbol, setSymbol] = useState("BTC/USDT");
  const [venue, setVenue] = useState("binance");
  const [timeframe, setTimeframe] = useState("1h");
  const [run, setRun] = useState<RunOut | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [autoAnalyze, setAutoAnalyze] = useState(true);

  // Auth gate
  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  // Market overview for the top ticker
  const { data: overview } = useQuery({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  // Run analysis
  const doAnalysis = useCallback(async () => {
    setAnalyzing(true);
    try {
      const result = await runAnalysis({ symbol, timeframe, strategy: "balanced" });
      setRun(result);
    } catch {
      setRun(null);
    } finally {
      setAnalyzing(false);
    }
  }, [symbol, timeframe]);

  // Auto-analyze on symbol/timeframe change
  useEffect(() => {
    if (!autoAnalyze || !user) return;
    doAnalysis();
  }, [symbol, timeframe, autoAnalyze, user, doAnalysis]);

  if (authLoading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      {/* Top Bar: Macro Ticker */}
      <TopTicker />

      {/* Control Bar */}
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <div className="flex items-center gap-2 mr-2">
          <Crosshair className="w-3.5 h-3.5 text-info" />
          <div className="hidden xl:block">
            <div className="terminal-label">Mission Control</div>
            <div className="text-[9px] text-muted font-mono">DECISION SUPPORT / HUMAN EXECUTION</div>
          </div>
        </div>
        <SymbolSearch onSelect={(sym) => setSymbol(sym)} />
        <VenueSelector value={venue} onChange={setVenue} />
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
        <label className="flex items-center gap-1 text-xs text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={autoAnalyze}
            onChange={(e) => setAutoAnalyze(e.target.checked)}
            className="accent-info"
          />
          Auto
        </label>
        <button
          onClick={doAnalysis}
          disabled={analyzing}
          className="ml-auto h-7 px-3 text-[10px] border border-info text-info hover:bg-info/10 disabled:opacity-50 font-mono flex items-center gap-2"
        >
          {analyzing ? <Activity className="w-3 h-3 animate-pulse" /> : <ScanLine className="w-3 h-3" />}
          {analyzing ? "ANALYZING" : "RUN COUNCIL"}
        </button>
        <button className="h-7 px-2 border border-border text-muted hover:text-primary font-mono text-[9px] flex items-center gap-1.5" title="Command palette">
          <Command className="w-3 h-3" /> K
        </button>
      </header>

      {/* Main Grid: 4-Panel Layout */}
      <div className="flex-1 min-h-0">
        <Group orientation="horizontal">
          {/* LEFT COLUMN: 70% — Chart + Arbitrage/Orderbook */}
          <Panel defaultSize={70} minSize={40}>
            <Group orientation="vertical">
              {/* Panel 1: TradingView Chart */}
              <Panel defaultSize={65} minSize={30}>
                <div className="h-full flex flex-col">
                  <div className="flex-1 relative min-h-0 border-l-2 border-l-info/30">
                    <div className="absolute z-10 left-2 top-2 pointer-events-none flex items-center gap-2 bg-bg/80 border border-border px-2 py-1 backdrop-blur">
                      <Focus className="w-3 h-3 text-info" />
                      <span className="font-mono text-[9px] text-primary">{symbol} / {timeframe.toUpperCase()} / {venue.toUpperCase()}</span>
                    </div>
                    <TradingViewChart
                      symbol={symbol}
                      venue={venue}
                      interval={timeframe}
                    />
                  </div>
                  {/* Quick stats strip */}
                  {overview && (
                    <div className="h-10 border-t border-border bg-panel flex items-stretch shrink-0">
                      {overview.tickers
                        .filter((t) => t.symbol === symbol)
                        .map((t) => (
                          <div key={t.symbol} className="flex items-center px-3 gap-3 text-xs font-mono">
                            <span className="text-lg font-bold text-primary">
                              ${t.last.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </span>
                            <span
                              className={
                                t.change_24h_pct != null && t.change_24h_pct >= 0
                                  ? "text-bullish"
                                  : "text-bearish"
                              }
                            >
                              {t.change_24h_pct != null
                                ? `${t.change_24h_pct >= 0 ? "+" : ""}${t.change_24h_pct.toFixed(2)}%`
                                : "—"}
                            </span>
                            <span className="text-muted">24h</span>
                            <span className="text-muted">
                              RSI: {t.rsi_14?.toFixed(1) ?? "—"} · {t.trend}
                            </span>
                          </div>
                        ))}
                      {!overview.tickers.some((t) => t.symbol === symbol) && (
                        <div className="flex items-center px-3 text-xs text-muted font-mono">
                          No data for {symbol}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Panel>

              <Separator className="h-1.5 bg-border hover:bg-info/30 transition-colors cursor-row-resize" />

              {/* Panel 3: Arbitrage & Orderbooks */}
              <Panel defaultSize={35} minSize={15}>
                <div className="h-full bg-panel overflow-hidden">
                  <ArbitrageOrderbookPanel symbol={symbol} />
                </div>
              </Panel>
            </Group>
          </Panel>

          <Separator className="w-1.5 bg-border hover:bg-info/30 transition-colors cursor-col-resize" />

          {/* RIGHT COLUMN: 30% — Agent Council + Debate/News */}
          <Panel defaultSize={30} minSize={20}>
            <Group orientation="vertical">
              {/* Panel 2: Agent Council */}
              <Panel defaultSize={55} minSize={30}>
                <div className="h-full bg-panel border-l border-border overflow-hidden">
                  <div className="flex items-center px-3 py-2 border-b border-border">
                    <h4 className="text-[10px] text-muted uppercase font-semibold tracking-wider">
                      Agent Council
                    </h4>
                  </div>
                  <div className="flex-1 overflow-auto">
                    <AgentCouncilPanel run={run} isAnalyzing={analyzing} />
                  </div>
                </div>
              </Panel>

              <Separator className="h-1.5 bg-border hover:bg-info/30 transition-colors cursor-row-resize" />

              {/* Panel 4: Debate Chamber & News */}
              <Panel defaultSize={45} minSize={20}>
                <div className="h-full bg-panel border-l border-border overflow-hidden">
                  <DebateNewsPanel symbol={symbol} run={run} />
                </div>
              </Panel>
            </Group>
          </Panel>
        </Group>
      </div>
    </div>
  );
}