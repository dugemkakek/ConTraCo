"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Star, Plus, X, RefreshCw } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { getMarketOverview, type MarketOverview } from "@/lib/api";

const STORAGE_KEY = "contraco-watchlist";

function loadWatchlist(): string[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveWatchlist(list: string[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

export default function WatchlistPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [input, setInput] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    setWatchlist(loadWatchlist());
  }, []);

  const addSymbol = useCallback((sym: string) => {
    const clean = sym.trim().toUpperCase();
    if (!clean) return;
    setWatchlist((prev) => {
      if (prev.includes(clean)) return prev;
      const next = [...prev, clean];
      saveWatchlist(next);
      return next;
    });
    setInput("");
  }, []);

  const removeSymbol = useCallback((sym: string) => {
    setWatchlist((prev) => {
      const next = prev.filter((s) => s !== sym);
      saveWatchlist(next);
      return next;
    });
  }, []);

  const { data: overview, isFetching, refetch } = useQuery({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const tickers = overview?.tickers ?? [];
  const watched = tickers.filter((t) => watchlist.includes(t.symbol));
  const unwatched = watchlist.filter((s) => !tickers.some((t) => t.symbol === s));

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <Star className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Watchlist</span>
        <span className="text-[9px] font-mono text-muted">{watchlist.length} SYMBOLS</span>
        <div className="ml-auto flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addSymbol(input)}
            placeholder="BTC/USDT"
            className="w-28 bg-bg border border-border px-2 py-1 text-[10px] font-mono text-primary placeholder:text-muted/50 focus:border-info focus:outline-none"
          />
          <button
            onClick={() => addSymbol(input)}
            className="h-7 px-2 text-[10px] border border-info text-info hover:bg-info/10 font-mono flex items-center gap-1"
          >
            <Plus className="w-3 h-3" /> ADD
          </button>
          <button
            onClick={() => refetch()}
            className="h-7 px-2 border border-border text-muted hover:text-primary font-mono"
          >
            <RefreshCw className={`w-3 h-3 ${isFetching ? "animate-spin" : ""}`} />
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto p-4">
        {watchlist.length === 0 && (
          <div className="grid place-content-center justify-items-center gap-3 text-center h-64">
            <Star className="w-10 h-10 text-muted/40" />
            <strong className="text-[11px] font-mono text-primary tracking-widest">EMPTY WATCHLIST</strong>
            <span className="text-[10px] text-muted">Add symbols above. Stored in your browser.</span>
          </div>
        )}

        {watched.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
            {watched.map((t) => (
              <div key={t.symbol} className="border border-border bg-panel p-3 group relative">
                <button
                  onClick={() => removeSymbol(t.symbol)}
                  className="absolute top-2 right-2 text-muted hover:text-bearish opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-mono text-sm font-bold text-primary">{t.symbol}</span>
                  <span className={`text-[10px] font-mono ${t.trend === "up" ? "text-bullish" : t.trend === "down" ? "text-bearish" : "text-muted"}`}>
                    {t.trend?.toUpperCase()}
                  </span>
                </div>
                <div className="flex items-end gap-3">
                  <span className="font-mono text-lg font-bold text-primary">
                    ${t.last?.toLocaleString(undefined, { minimumFractionDigits: 2 }) ?? "—"}
                  </span>
                  <span className={`font-mono text-xs ${(t.change_24h_pct ?? 0) >= 0 ? "text-bullish" : "text-bearish"}`}>
                    {(t.change_24h_pct ?? 0) >= 0 ? "+" : ""}{(t.change_24h_pct ?? 0).toFixed(2)}%
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3 text-[9px] font-mono text-muted">
                  <span>RSI: {t.rsi_14?.toFixed(1) ?? "—"}</span>
                  <span>H: ${t.high_24h?.toLocaleString() ?? "—"}</span>
                  <span>L: ${t.low_24h?.toLocaleString() ?? "—"}</span>
                </div>
                {t.sparkline && t.sparkline.length > 1 && (
                  <svg viewBox="0 0 120 30" className="w-full h-8 mt-2" preserveAspectRatio="none">
                    <polyline
                      points={t.sparkline.map((v, i) => `${(i / (t.sparkline!.length - 1)) * 120},${30 - ((v - Math.min(...t.sparkline!)) / (Math.max(...t.sparkline!) - Math.min(...t.sparkline!) || 1)) * 28 - 1}`).join(" ")}
                      fill="none"
                      stroke={(t.change_24h_pct ?? 0) >= 0 ? "#10b981" : "#f43f5e"}
                      strokeWidth="1.5"
                    />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}

        {unwatched.length > 0 && (
          <div className="mt-4 text-[9px] font-mono text-muted">
            Not in market overview: {unwatched.join(", ")} (add to Binance-supported pairs or check symbol format)
          </div>
        )}
      </main>
    </div>
  );
}
