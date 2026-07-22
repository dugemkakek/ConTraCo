"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  runAnalysis,
  type RunOut,
} from "@/lib/api";
import { TradingViewChart } from "@/components/chart/TradingViewChart";
import { TimeframeSelector } from "@/components/terminal/TimeframeSelector";
import { AnalysisTabs } from "@/components/decision/AnalysisTabs";
import { useAuth } from "@/lib/auth-context";

const DEFAULT_WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];

export default function TerminalPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useParams<{ symbol: string }>();
  const searchParams = useSearchParams();
  const symbol = (params.symbol ?? "BTC-USDT").toString();
  const displaySymbol = symbol.replace("-", "/");
  const venueFromUrl = searchParams.get("venue") || "binance";

  const [timeframe, setTimeframe] = useState("1h");
  const [venue, setVenue] = useState(venueFromUrl);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunOut | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  // Keep venue in sync with URL
  useEffect(() => {
    setVenue(venueFromUrl);
  }, [venueFromUrl]);

  // Auth gate
  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  async function onRunAnalysis() {
    setAnalyzing(true);
    setError(null);
    try {
      const result = await runAnalysis({
        symbol: displaySymbol,
        timeframe,
        strategy: "balanced",
      });
      setRun(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  // Auto-analysis when symbol/timeframe changes (if toggle is on)
  const [autoAnalyze, setAutoAnalyze] = useState(false);
  useEffect(() => {
    if (!autoAnalyze || !user) return;
    setAnalyzing(true);
    runAnalysis({ symbol: displaySymbol, timeframe, strategy: "balanced" })
      .then((result) => setRun(result))
      .catch(() => setRun(null))
      .finally(() => setAnalyzing(false));
  }, [displaySymbol, timeframe, autoAnalyze, user]);

  async function onLoadRun(runId: number) {
    try {
      const { request } = await import("@/lib/api");
      const res = await request<any>(`/api/v1/analysis/runs/${runId}`);
      setRun(res);
    } catch {
      // ignore
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center gap-3 px-4 py-3 border-b border-border bg-panel flex-wrap">
        <span className="font-semibold text-sm">{displaySymbol}</span>
        <select
          value={venue}
          onChange={(e) => router.push(`/terminal/${symbol}?venue=${e.target.value}`)}
          className="bg-border/40 border border-border rounded px-2 py-1 text-xs outline-none focus:border-info text-primary"
        >
          <option value="gateio">Gate.io</option>
          <option value="mock">Mock</option>
        </select>
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
        <label className="flex items-center gap-1 text-xs text-muted cursor-pointer ml-2">
          <input
            type="checkbox"
            checked={autoAnalyze}
            onChange={(e) => setAutoAnalyze(e.target.checked)}
            className="accent-info"
          />
          Auto
        </label>
        <button
          onClick={onRunAnalysis}
          disabled={analyzing}
          data-testid="run-analysis-button"
          className="ml-auto px-3 py-1.5 text-xs rounded-md border border-info text-info hover:bg-info/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {analyzing ? "Running…" : "Run Analysis"}
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-56 border-r border-border bg-panel p-3 hidden md:flex flex-col gap-2">
          <h3 className="text-xs font-semibold text-muted uppercase">Watchlist</h3>
          {DEFAULT_WATCHLIST.map((s) => (
            <Link
              key={s}
              href={`/terminal/${s.replace("/", "-")}`}
              className={`text-sm px-2 py-1 rounded-md ${
                displaySymbol === s
                  ? "bg-info/20 text-info"
                  : "text-primary hover:bg-border/40"
              }`}
            >
              {s}
            </Link>
          ))}
          <Link
            href="/scan"
            className="text-xs text-muted hover:text-primary mt-2 px-2 py-1"
          >
            Open Scanner →
          </Link>
        </aside>

        <main className="flex-1 p-4 flex flex-col gap-3 overflow-auto">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-semibold">{displaySymbol}</h1>
          </div>

          <div className="bg-panel border border-border rounded-md p-1">
            <TradingViewChart
              symbol={displaySymbol}
              venue={venue}
              interval={timeframe}
            />
          </div>
        </main>

        <aside className="w-96 border-l border-border bg-panel flex flex-col overflow-hidden hidden lg:flex">
          <AnalysisTabs
            run={run}
            isAnalyzing={analyzing}
            symbol={displaySymbol}
            onSelectRun={onLoadRun}
          />
        </aside>
      </div>
    </div>
  );
}
