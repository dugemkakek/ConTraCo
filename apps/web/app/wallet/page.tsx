"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Wallet, Search, RefreshCw, ExternalLink, Tag } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { analyzeWallet } from "@/lib/api";

type Portfolio = {
  chain: string;
  token_count: number;
  total_usd_estimate: number;
  top_tokens: { symbol?: string; name?: string; balance?: number; usd_value?: number }[];
  note?: string | null;
  error?: string | null;
};

type WalletResult = {
  address: string;
  chains: string[];
  total_usd_estimate: number;
  portfolios: Portfolio[];
  ethereum_behavior_score: { score?: number; label?: string };
  council_tags: string[];
  council_summary: {
    wallet_quality_score?: number;
    cross_chain_exposure_usd?: number;
    chains_active?: number;
  };
};

function fmtUsd(v?: number): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

export default function WalletPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [address, setAddress] = useState("");
  const [data, setData] = useState<WalletResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingResult, setLoadingResult] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const runAnalysis = async () => {
    const addr = address.trim();
    if (!addr.startsWith("0x") || addr.length !== 42) {
      setError("Enter a valid 0x address (42 chars)");
      return;
    }
    setError(null);
    setLoadingResult(true);
    try {
      const res = await analyzeWallet(addr);
      setData(res as WalletResult);
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setData(null);
    } finally {
      setLoadingResult(false);
    }
  };

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
        <Wallet className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Wallet Analyzer</span>
        <span className="text-[9px] font-mono text-muted">MULTI-CHAIN · COUNCIL SCORED</span>
        <div className="ml-auto flex items-center gap-2">
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runAnalysis()}
            placeholder="0x… wallet address"
            className="w-72 bg-bg border border-border px-2 py-1 text-[10px] font-mono text-primary placeholder:text-muted/50 focus:border-info focus:outline-none"
          />
          <button
            onClick={runAnalysis}
            disabled={loadingResult}
            className="h-7 px-3 text-[10px] border border-info text-info hover:bg-info/10 font-mono flex items-center gap-2 disabled:opacity-50"
          >
            {loadingResult ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
            ANALYZE
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-4">
        {error && (
          <div className="border border-bearish bg-bearish/10 text-bearish text-[10px] font-mono px-3 py-2">
            {error}
          </div>
        )}

        {!data && !error && (
          <div className="grid place-content-center justify-items-center gap-3 text-center h-64">
            <Wallet className="w-10 h-10 text-muted/40" />
            <strong className="text-[11px] font-mono text-primary tracking-widest">ENTER A WALLET ADDRESS</strong>
            <span className="text-[10px] text-muted">
              Analyzes ETH, Base, Arbitrum, Optimism, Polygon. Free APIs, no key.
            </span>
          </div>
        )}

        {data && (
          <>
            {/* Summary row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div className="border border-border bg-panel p-3">
                <div className="text-[8px] font-mono text-muted mb-1">TOTAL ESTIMATE</div>
                <div className="text-lg font-mono font-bold text-primary">{fmtUsd(data.total_usd_estimate)}</div>
              </div>
              <div className="border border-border bg-panel p-3">
                <div className="text-[8px] font-mono text-muted mb-1">QUALITY SCORE</div>
                <div className="text-lg font-mono font-bold text-primary">
                  {data.ethereum_behavior_score?.score ?? "—"}
                  <span className="text-[9px] text-muted ml-1">/100</span>
                </div>
              </div>
              <div className="border border-border bg-panel p-3">
                <div className="text-[8px] font-mono text-muted mb-1">CHAINS ACTIVE</div>
                <div className="text-lg font-mono font-bold text-primary">
                  {data.council_summary?.chains_active ?? 0}
                  <span className="text-[9px] text-muted ml-1">/ {data.chains.length}</span>
                </div>
              </div>
              <div className="border border-border bg-panel p-3">
                <div className="text-[8px] font-mono text-muted mb-1">COUNCIL TAGS</div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {data.council_tags.length === 0 && <span className="text-[9px] text-muted">none</span>}
                  {data.council_tags.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 text-[8px] font-mono border border-info/40 text-info px-1.5 py-0.5">
                      <Tag className="w-2.5 h-2.5" /> {t}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Address link */}
            <div className="text-[9px] font-mono text-muted flex items-center gap-1">
              <ExternalLink className="w-3 h-3" />
              <a
                href={`https://etherscan.io/address/${data.address}`}
                target="_blank"
                rel="noreferrer"
                className="text-info hover:underline"
              >
                {data.address}
              </a>
            </div>

            {/* Per-chain portfolios */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {data.portfolios.map((p) => (
                <div key={p.chain} className="border border-border bg-panel p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-mono font-bold text-primary uppercase">{p.chain}</span>
                    <span className="text-[9px] font-mono text-muted">{fmtUsd(p.total_usd_estimate)}</span>
                  </div>
                  {p.error && (
                    <div className="text-[9px] font-mono text-bearish mb-1">{p.error}</div>
                  )}
                  {p.note && (
                    <div className="text-[9px] font-mono text-muted mb-1">{p.note}</div>
                  )}
                  {p.token_count === 0 && !p.error && (
                    <div className="text-[9px] font-mono text-muted italic">No tokens found</div>
                  )}
                  {p.top_tokens.length > 0 && (
                    <table className="w-full text-[9px] font-mono">
                      <thead className="text-muted">
                        <tr>
                          <th className="text-left pb-1">TOKEN</th>
                          <th className="text-right pb-1">USD</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/50">
                        {p.top_tokens.map((t, i) => (
                          <tr key={i}>
                            <td className="py-0.5 text-primary">{t.symbol ?? "?"}</td>
                            <td className="py-0.5 text-right text-muted">{fmtUsd(t.usd_value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </div>

            <p className="text-[8px] font-mono text-muted">
              DATA: ETHERSCAN-FREE + COINGECKO. SCORES ARE HEURISTIC — NOT FINANCIAL ADVICE.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
