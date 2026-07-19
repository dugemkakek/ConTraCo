"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { getMarketOverview, runAnalysis, type RunOut } from "@/lib/api";
import { TradingViewChart } from "@/components/chart/TradingViewChart";
import { TimeframeSelector } from "@/components/terminal/TimeframeSelector";
import { AnalysisTabs } from "@/components/decision/AnalysisTabs";
import { SymbolSearch } from "@/components/terminal/SymbolSearch";
import { VenueSelector } from "@/components/terminal/VenueSelector";
import { MarketConditionCard } from "@/components/dashboard/MarketConditionCard";
import { BreadthGauge } from "@/components/dashboard/BreadthGauge";

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [symbol, setSymbol] = useState("BTC/USDT");
  const [venue, setVenue] = useState("gateio");
  const [timeframe, setTimeframe] = useState("1h");
  const [run, setRun] = useState<RunOut | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [autoAnalyze, setAutoAnalyze] = useState(true);

  // Auth gate
  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  // Market overview for the top cards
  const { data: overview } = useQuery({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  // Run analysis
  async function doAnalysis() {
    setAnalyzing(true);
    try {
      const result = await runAnalysis({ symbol, timeframe, strategy: "balanced" });
      setRun(result);
    } catch {
      setRun(null);
    } finally {
      setAnalyzing(false);
    }
  }

  // Auto-analyze on symbol/timeframe change
  useEffect(() => {
    if (!autoAnalyze || !user) return;
    setAnalyzing(true);
    runAnalysis({ symbol, timeframe, strategy: "balanced" })
      .then((result) => setRun(result))
      .catch(() => setRun(null))
      .finally(() => setAnalyzing(false));
  }, [symbol, timeframe, autoAnalyze, user]);

  async function onLoadRun(runId: number) {
    try {
      const { request } = await import("@/lib/api");
      const res = await request<any>(`/api/v1/analysis/runs/${runId}`);
      setRun(res);
    } catch {
      // ignore
    }
  }

  // Scanner data
  const { data: notableScans } = useQuery({
    queryKey: ["notable-scans"],
    queryFn: async () => {
      const { request } = await import("@/lib/api");
      const status: { notable: { symbol: string; final_state: string | null; run_id: number }[] } =
        await request("/api/v1/scanner/status");
      return status.notable ?? [];
    },
    refetchInterval: 30_000,
    enabled: !!user,
  });

  return (
    <div className="h-screen flex flex-col bg-bg">
      {/* Top bar */}
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
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
          className="ml-auto px-3 py-1 text-xs rounded border border-info text-info hover:bg-info/20 disabled:opacity-50"
        >
          {analyzing ? "…" : "Analyze"}
        </button>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chart area */}
        <div className="flex-[7] min-w-0 flex flex-col">
          <div className="flex-1 relative">
            <TradingViewChart
              symbol={symbol}
              venue={venue}
              interval={timeframe}
              height={0} /* will fill container via flex */
            />
          </div>
          {/* Quick stats strip below chart */}
          {overview && (
            <div className="h-14 border-t border-border bg-panel flex items-stretch">
              {overview.tickers.filter((t) => t.symbol === symbol).map((t) => (
                <div key={t.symbol} className="flex items-center px-3 gap-3 text-xs">
                  <span className="text-lg font-bold">
                    ${t.last.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                  <span className={t.change_24h_pct != null && t.change_24h_pct >= 0 ? "text-bullish" : "text-bearish"}>
                    {t.change_24h_pct != null ? `${t.change_24h_pct >= 0 ? "+" : ""}${t.change_24h_pct.toFixed(2)}%` : "—"}
                  </span>
                  <span className="text-muted">24h</span>
                  <span className="text-muted">
                    RSI: {t.rsi_14?.toFixed(1) ?? "—"} · {t.trend}
                  </span>
                </div>
              ))}
              {(!overview.tickers.some((t) => t.symbol === symbol)) && (
                <div className="flex items-center px-3 text-xs text-muted">
                  No data for {symbol}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Side panel */}
        <aside className="flex-[3] min-w-0 border-l border-border bg-panel flex flex-col overflow-hidden">
          <AnalysisTabs
            run={run}
            isAnalyzing={analyzing}
            symbol={symbol}
            onSelectRun={onLoadRun}
          />
        </aside>
      </div>

      {/* Bottom strip */}
      <div className="h-36 border-t border-border bg-panel flex overflow-hidden shrink-0">
        {/* Market condition cards */}
        <div className="flex-[5] flex items-stretch gap-2 p-2 overflow-auto">
          {overview && (
            <>
              <MarketConditionCard overview={overview} />
              <BreadthGauge breadth={overview.breadth} />
            </>
          )}
        </div>

        {/* Scanner / notable scans */}
        <div className="flex-[4] border-l border-border p-2 overflow-auto">
          <h4 className="text-[10px] text-muted uppercase font-semibold mb-1">Scanner</h4>
          {notableScans?.length ? (
            <div className="flex flex-col gap-0.5">
              {notableScans.slice(0, 6).map((s, i) => (
                <button
                  key={`${s.symbol}-${i}`}
                  onClick={() => setSymbol(s.symbol)}
                  className="flex items-center gap-2 text-xs px-1.5 py-0.5 hover:bg-border/40 rounded text-left"
                >
                  <span className="text-primary">{s.symbol.replace("/USDT", "")}</span>
                  <span className="text-muted">{s.final_state ?? "—"}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted">No recent scans</p>
          )}
        </div>
      </div>
    </div>
  );
}
