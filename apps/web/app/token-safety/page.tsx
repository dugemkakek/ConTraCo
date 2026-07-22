"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Shield, Search, AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { getTokenSafety, type TokenSafety } from "@/lib/api";

const RISK_COLORS: Record<string, string> = {
  safe: "text-bullish",
  caution: "text-amber-400",
  danger: "text-bearish",
  unknown: "text-muted",
};

const RISK_ICONS: Record<string, typeof CheckCircle> = {
  safe: CheckCircle,
  caution: AlertTriangle,
  danger: XCircle,
  unknown: Shield,
};

function BoolCell({ label, value, invert = false }: { label: string; value: boolean | null; invert?: boolean }) {
  const isBad = value === null ? null : invert ? !value : value;
  return (
    <div className="bg-panel px-3 py-2">
      <div className="terminal-label mb-1">{label}</div>
      <div className={`font-mono text-xs font-semibold ${isBad === null ? "text-muted" : isBad ? "text-bearish" : "text-bullish"}`}>
        {value === null ? "—" : value ? "YES" : "NO"}
      </div>
    </div>
  );
}

export default function TokenSafetyPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [address, setAddress] = useState("");
  const [chainId, setChainId] = useState("1");
  const [result, setResult] = useState<TokenSafety | null>(null);
  const [loadingScan, setLoadingScan] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  async function onScan() {
    if (!address.trim()) return;
    setLoadingScan(true);
    setError(null);
    try {
      const r = await getTokenSafety(address.trim(), Number(chainId));
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "scan failed");
    } finally {
      setLoadingScan(false);
    }
  }

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const RiskIcon = result ? (RISK_ICONS[result.risk_level] ?? Shield) : Shield;

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <Shield className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Token Safety Analyzer</span>
        <span className="text-[9px] font-mono text-muted">HONEYPOT · RUG · TAX CHECK</span>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-4 max-w-3xl mx-auto w-full">
        {/* Search */}
        <div className="flex gap-2">
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onScan()}
            placeholder="Token contract address (0x...)"
            className="flex-1 bg-panel border border-border px-3 py-2 text-xs font-mono text-primary placeholder:text-muted/50 focus:border-info focus:outline-none"
          />
          <select
            value={chainId}
            onChange={(e) => setChainId(e.target.value)}
            className="bg-panel border border-border px-2 py-2 text-xs font-mono text-primary"
          >
            <option value="1">ETH</option>
            <option value="56">BSC</option>
            <option value="137">Polygon</option>
            <option value="42161">Arbitrum</option>
            <option value="8453">Base</option>
            <option value="43114">Avalanche</option>
          </select>
          <button
            onClick={onScan}
            disabled={loadingScan || !address.trim()}
            className="h-9 px-4 text-[10px] border border-info text-info hover:bg-info/10 disabled:opacity-50 font-mono flex items-center gap-2"
          >
            <Search className={`w-3 h-3 ${loadingScan ? "animate-pulse" : ""}`} />
            {loadingScan ? "SCANNING" : "SCAN"}
          </button>
        </div>

        {error && (
          <p className="text-[10px] font-mono text-bearish">{error}</p>
        )}

        {result && (
          <>
            {/* Verdict */}
            <div className={`border p-4 flex items-center gap-3 ${
              result.risk_level === "safe" ? "border-bullish/40 bg-bullish/5" :
              result.risk_level === "danger" ? "border-bearish/40 bg-bearish/5" :
              result.risk_level === "caution" ? "border-amber-400/40 bg-amber-400/5" :
              "border-border bg-panel"
            }`}>
              <RiskIcon className={`w-8 h-8 ${RISK_COLORS[result.risk_level] ?? "text-muted"}`} />
              <div>
                <div className={`text-lg font-bold font-mono uppercase ${RISK_COLORS[result.risk_level] ?? "text-muted"}`}>
                  {result.risk_level}
                </div>
                <div className="text-[10px] font-mono text-muted truncate max-w-md">{result.address}</div>
              </div>
              {result.risk_flags.length > 0 && (
                <div className="ml-auto flex flex-wrap gap-1 justify-end max-w-xs">
                  {result.risk_flags.map((f) => (
                    <span key={f} className="px-1.5 py-0.5 border border-bearish/40 text-bearish text-[8px] font-mono bg-bearish/10">
                      {f}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Detail grid */}
            <div className="grid grid-cols-3 md:grid-cols-4 gap-px bg-border border border-border">
              <BoolCell label="HONEYPOT" value={result.is_honeypot} />
              <BoolCell label="MINTABLE" value={result.is_mintable} />
              <BoolCell label="OWNERSHIP TAKEBACK" value={result.can_take_back_ownership} />
              <BoolCell label="OWNER CHANGE BAL" value={result.owner_change_balance} />
              <BoolCell label="PROXY" value={result.is_proxy} />
              <BoolCell label="OPEN SOURCE" value={result.is_open_source} invert />
              <BoolCell label="BLACKLIST FN" value={result.is_blacklisted} />
              <BoolCell label="SLIPPAGE MOD" value={result.slippage_modifiable} />
              <div className="bg-panel px-3 py-2">
                <div className="terminal-label mb-1">BUY TAX</div>
                <div className={`font-mono text-xs font-semibold ${(result.buy_tax ?? 0) > 0.1 ? "text-bearish" : "text-primary"}`}>
                  {result.buy_tax != null ? `${(result.buy_tax * 100).toFixed(1)}%` : "—"}
                </div>
              </div>
              <div className="bg-panel px-3 py-2">
                <div className="terminal-label mb-1">SELL TAX</div>
                <div className={`font-mono text-xs font-semibold ${(result.sell_tax ?? 0) > 0.1 ? "text-bearish" : "text-primary"}`}>
                  {result.sell_tax != null ? `${(result.sell_tax * 100).toFixed(1)}%` : "—"}
                </div>
              </div>
              <div className="bg-panel px-3 py-2">
                <div className="terminal-label mb-1">HOLDERS</div>
                <div className="font-mono text-xs font-semibold text-primary">
                  {result.holder_count?.toLocaleString() ?? "—"}
                </div>
              </div>
              <div className="bg-panel px-3 py-2">
                <div className="terminal-label mb-1">LP HOLDERS</div>
                <div className="font-mono text-xs font-semibold text-primary">
                  {result.lp_holders_count?.toLocaleString() ?? "—"}
                </div>
              </div>
            </div>

            <p className="text-[8px] font-mono text-muted">
              DATA: GOPLUS LABS (FREE, NO KEY). RISK ASSESSMENT IS AUTOMATED — ALWAYS DYOR. NOT FINANCIAL ADVICE.
            </p>
          </>
        )}

        {!result && !loadingScan && (
          <div className="flex-1 grid place-content-center justify-items-center gap-3 text-center">
            <Shield className="w-10 h-10 text-muted/40" />
            <strong className="text-[11px] font-mono text-primary tracking-widest">PASTE A CONTRACT ADDRESS</strong>
            <span className="text-[10px] text-muted">Scan any ERC-20/BEP-20 token for honeypot, rug, and tax risks.</span>
          </div>
        )}
      </main>
    </div>
  );
}
