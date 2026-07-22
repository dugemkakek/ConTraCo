"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Flame, TrendingUp, RefreshCw, ExternalLink, Shield } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { getTrenches, type TrenchPair, type TrendingCoin } from "@/lib/api";

function fmtUsd(v?: number): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

function PairTable({ pairs, refreshing }: { pairs: TrenchPair[]; refreshing: boolean }) {
  const dexPairs = pairs.filter((p) => p.base_token);
  return (
    <section className="border border-border bg-panel">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Flame className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">DEX Volume Leaders</span>
        <span className="ml-auto text-[9px] font-mono text-muted">{dexPairs.length} PAIRS</span>
        {refreshing && <RefreshCw className="w-3 h-3 text-info animate-spin" />}
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-[10px] font-mono">
          <thead className="bg-bg text-muted">
            <tr>
              {["PAIR", "CHAIN", "DEX", "PRICE", "VOL 24H", "VOL 1H", "Δ24H", "LIQ", "FDV", ""].map((h) => (
                <th key={h} className="text-left px-3 py-2 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {dexPairs.map((p, i) => (
              <tr key={i} className="hover:bg-info/5 transition-colors">
                <td className="px-3 py-2 text-primary font-semibold whitespace-nowrap">
                  {p.base_token}/{p.quote_token}
                </td>
                <td className="px-3 py-2 text-muted">{p.chain}</td>
                <td className="px-3 py-2 text-muted">{p.dex}</td>
                <td className="px-3 py-2">${(p.price_usd ?? 0) < 0.01 ? (p.price_usd ?? 0).toPrecision(3) : (p.price_usd ?? 0).toLocaleString()}</td>
                <td className="px-3 py-2">{fmtUsd(p.volume_24h)}</td>
                <td className="px-3 py-2">{fmtUsd(p.volume_1h)}</td>
                <td className={`px-3 py-2 ${(p.price_change_24h ?? 0) >= 0 ? "text-bullish" : "text-bearish"}`}>
                  {(p.price_change_24h ?? 0) >= 0 ? "+" : ""}{(p.price_change_24h ?? 0).toFixed(1)}%
                </td>
                <td className="px-3 py-2">{fmtUsd(p.liquidity_usd)}</td>
                <td className="px-3 py-2">{fmtUsd(p.fdv)}</td>
                <td className="px-3 py-2">
                  {p.url && (
                    <a href={p.url} target="_blank" rel="noreferrer" className="text-info hover:underline">
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </td>
              </tr>
            ))}
            {dexPairs.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-6 text-center text-muted">No pairs found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TrendingPanel({ coins }: { coins: TrendingCoin[] }) {
  return (
    <section className="border border-border bg-panel">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <TrendingUp className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">CoinGecko Trending</span>
      </header>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-border">
        {coins.map((c, i) => (
          <div key={i} className="bg-panel px-3 py-2 flex items-center gap-2">
            {c.thumb && <img src={c.thumb} alt="" className="w-5 h-5 rounded-full" />}
            <div className="min-w-0">
              <div className="text-[10px] font-mono text-primary font-semibold truncate">{c.symbol}</div>
              <div className="text-[8px] text-muted truncate">#{c.market_cap_rank ?? "?"} · {c.name}</div>
            </div>
          </div>
        ))}
        {coins.length === 0 && (
          <div className="col-span-full px-3 py-4 text-center text-muted text-[10px]">No trending data.</div>
        )}
      </div>
    </section>
  );
}

export default function TrenchesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["trenches"],
    queryFn: () => getTrenches(20),
    refetchInterval: 60_000,
    enabled: !!user,
  });

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <Flame className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Trenches — Opportunity Scanner</span>
        <span className="text-[9px] font-mono text-muted">VOLUME · TRENDING · NEW PAIRS</span>
        <button
          onClick={() => refetch()}
          className="ml-auto h-7 px-3 text-[10px] border border-info text-info hover:bg-info/10 font-mono flex items-center gap-2"
        >
          <RefreshCw className={`w-3 h-3 ${isFetching ? "animate-spin" : ""}`} />
          RESCAN
        </button>
      </header>
      <main className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-4">
        <TrendingPanel coins={data?.trending_coins ?? []} />
        <PairTable pairs={data?.pairs ?? []} refreshing={isFetching} />
        <p className="text-[8px] font-mono text-muted">
          DATA: DEX SCREENER + COINGECKO (FREE, NO KEY). NOT EXECUTION ADVICE — HUMAN DECIDES.
        </p>
      </main>
    </div>
  );
}
