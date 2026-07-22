"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, RefreshCw, Zap } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  getYieldOpportunities,
  getCexDexSpreads,
  type YieldOpportunity,
  type CexDexSpread,
} from "@/lib/api";

function YieldTable({ opps, refreshing }: { opps: YieldOpportunity[]; refreshing: boolean }) {
  return (
    <section className="border border-border bg-panel">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Zap className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Delta-Neutral Yield / Funding Arb</span>
        <span className="ml-auto text-[9px] font-mono text-muted">{opps.length} OPPS</span>
        {refreshing && <RefreshCw className="w-3 h-3 text-info animate-spin" />}
      </header>
      <table className="w-full text-[10px] font-mono">
        <thead className="bg-bg text-muted">
          <tr>
            {["PAIR", "LONG", "SHORT", "SPOT", "PERP", "FUNDING", "NET APY", "CONF"].map((h) => (
              <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {opps.map((o, i) => (
            <tr key={i} className="hover:bg-info/5 transition-colors">
              <td className="px-3 py-2 text-primary font-semibold">{o.symbol}</td>
              <td className="px-3 py-2 text-bullish">{o.long_venue}</td>
              <td className="px-3 py-2 text-bearish">{o.short_venue}</td>
              <td className="px-3 py-2">${o.spot_price.toLocaleString()}</td>
              <td className="px-3 py-2">${o.perp_price.toLocaleString()}</td>
              <td className={`px-3 py-2 ${o.funding_rate >= 0 ? "text-bullish" : "text-bearish"}`}>
                {(o.funding_rate * 100).toFixed(4)}%
              </td>
              <td className={`px-3 py-2 font-semibold ${o.net_apy >= 0 ? "text-bullish" : "text-bearish"}`}>
                {o.net_apy.toFixed(1)}%
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-1.5">
                  <div className="w-12 h-1.5 bg-bg overflow-hidden">
                    <div className="h-full bg-info" style={{ width: `${o.confidence * 100}%` }} />
                  </div>
                  <span className="text-muted">{Math.round(o.confidence * 100)}</span>
                </div>
              </td>
            </tr>
          ))}
          {opps.length === 0 && (
            <tr><td colSpan={8} className="px-3 py-6 text-center text-muted">No opportunities found.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function SpreadTable({ spreads, refreshing }: { spreads: CexDexSpread[]; refreshing: boolean }) {
  return (
    <section className="border border-border bg-panel">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <ArrowLeftRight className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">CEX / DEX Spread Matrix</span>
        <span className="ml-auto text-[9px] font-mono text-muted">{spreads.length} PAIRS</span>
        {refreshing && <RefreshCw className="w-3 h-3 text-info animate-spin" />}
      </header>
      <table className="w-full text-[10px] font-mono">
        <thead className="bg-bg text-muted">
          <tr>
            {["PAIR", "CEX", "CEX PRICE", "DEX", "DEX PRICE", "SPREAD", "NET AFTER GAS", "EXEC"].map((h) => (
              <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {spreads.map((s, i) => (
            <tr key={i} className="hover:bg-info/5 transition-colors">
              <td className="px-3 py-2 text-primary font-semibold">{s.symbol}</td>
              <td className="px-3 py-2">{s.cex_venue}</td>
              <td className="px-3 py-2">${s.cex_price.toLocaleString()}</td>
              <td className="px-3 py-2">{s.dex_venue}</td>
              <td className="px-3 py-2">${s.dex_price.toLocaleString()}</td>
              <td className={`px-3 py-2 font-semibold ${s.spread_pct >= 0 ? "text-bullish" : "text-bearish"}`}>
                {s.spread_pct.toFixed(2)}%
              </td>
              <td className={`px-3 py-2 ${s.net_profit_after_gas >= 0 ? "text-bullish" : "text-bearish"}`}>
                {s.net_profit_after_gas.toFixed(2)}%
              </td>
              <td className="px-3 py-2">
                <span
                  className={`px-1.5 py-0.5 border text-[8px] ${
                    s.executable
                      ? "border-bullish/50 text-bullish bg-bullish/10"
                      : "border-border text-muted"
                  }`}
                >
                  {s.executable ? "LIVE" : "NO"}
                </span>
              </td>
            </tr>
          ))}
          {spreads.length === 0 && (
            <tr><td colSpan={8} className="px-3 py-6 text-center text-muted">No spreads detected.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

export default function ArbitragePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [lastScan, setLastScan] = useState<Date | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const yieldQ = useQuery({
    queryKey: ["arb-yield"],
    queryFn: getYieldOpportunities,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  const spreadQ = useQuery({
    queryKey: ["arb-spreads"],
    queryFn: getCexDexSpreads,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  useEffect(() => {
    if (yieldQ.dataUpdatedAt) setLastScan(new Date(yieldQ.dataUpdatedAt));
  }, [yieldQ.dataUpdatedAt]);

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
        <ArrowLeftRight className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Arbitrage Matrix</span>
        <span className="text-[9px] font-mono text-muted">CEX/DEX SPREADS + FUNDING ARB</span>
        <div className="ml-auto flex items-center gap-3">
          {lastScan && (
            <span className="text-[9px] font-mono text-muted">
              LAST SCAN {lastScan.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
          )}
          <button
            onClick={() => { yieldQ.refetch(); spreadQ.refetch(); }}
            className="h-7 px-3 text-[10px] border border-info text-info hover:bg-info/10 font-mono flex items-center gap-2"
          >
            <RefreshCw className={`w-3 h-3 ${yieldQ.isFetching ? "animate-spin" : ""}`} />
            RESCAN
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-4">
        <YieldTable opps={yieldQ.data?.opportunities ?? []} refreshing={yieldQ.isFetching} />
        <SpreadTable spreads={spreadQ.data?.spreads ?? []} refreshing={spreadQ.isFetching} />
        <p className="text-[8px] font-mono text-muted leading-relaxed">
          DATA SOURCE: GATE.IO PAPER VENUE (SIM). REAL MULTI-VENUE QUOTES + TRIANGULAR SCANNER WIRED IN PHASE 13.
          SPREADS SHOWN AFTER ESTIMATED GAS. NOT EXECUTION ADVICE — HUMAN DECIDES.
        </p>
      </main>
    </div>
  );
}
