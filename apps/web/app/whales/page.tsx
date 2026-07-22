"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Waves, RefreshCw, ExternalLink } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { getWhaleMovements, type WhaleMovement } from "@/lib/api";

export default function WhalesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [minBtc, setMinBtc] = useState("100");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["whales", minBtc],
    queryFn: () => getWhaleMovements(Number(minBtc), 30),
    refetchInterval: 120_000,
    enabled: !!user,
  });

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const movements = data?.movements ?? [];

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <Waves className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Smart Wallet Tracker — Whale Movements</span>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-[9px] font-mono text-muted">MIN BTC</label>
          <input
            type="number"
            value={minBtc}
            onChange={(e) => setMinBtc(e.target.value)}
            className="w-20 bg-bg border border-border px-2 py-1 text-[10px] font-mono text-primary"
          />
          <button
            onClick={() => refetch()}
            className="h-7 px-3 text-[10px] border border-info text-info hover:bg-info/10 font-mono flex items-center gap-2"
          >
            <RefreshCw className={`w-3 h-3 ${isFetching ? "animate-spin" : ""}`} />
            RESCAN
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto p-4">
        <section className="border border-border bg-panel">
          <header className="flex items-center gap-2 px-3 py-2 border-b border-border">
            <span className="terminal-label">Latest Block — Large Transactions</span>
            <span className="ml-auto text-[9px] font-mono text-muted">{movements.length} TXS ≥ {minBtc} BTC</span>
          </header>
          <table className="w-full text-[10px] font-mono">
            <thead className="bg-bg text-muted">
              <tr>
                {["TX HASH", "BTC", "USD EST", "INPUTS", "OUTPUTS", "TIME", ""].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {movements.map((m, i) => (
                <tr key={i} className="hover:bg-info/5 transition-colors">
                  <td className="px-3 py-2 text-info truncate max-w-[180px]">{m.tx_hash.slice(0, 16)}…</td>
                  <td className="px-3 py-2 text-primary font-semibold">{m.btc_amount.toLocaleString()} BTC</td>
                  <td className="px-3 py-2 text-bullish">${m.usd_estimate.toLocaleString()}</td>
                  <td className="px-3 py-2 text-muted">{m.inputs}</td>
                  <td className="px-3 py-2 text-muted">{m.outputs}</td>
                  <td className="px-3 py-2 text-muted">
                    {m.time ? new Date(m.time * 1000).toLocaleTimeString() : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <a
                      href={`https://blockchain.info/tx/${m.tx_hash}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-info hover:underline"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </td>
                </tr>
              ))}
              {movements.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-muted">No whale movements found in latest block.</td></tr>
              )}
            </tbody>
          </table>
        </section>
        <p className="text-[8px] font-mono text-muted mt-3">
          DATA: BLOCKCHAIN.INFO (FREE, NO KEY). SHOWS LARGE BTC TXS FROM LATEST BLOCK. NOT FINANCIAL ADVICE.
        </p>
      </main>
    </div>
  );
}
