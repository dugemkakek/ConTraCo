"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical, Play, Trash2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  runBacktest,
  listBacktests,
  deleteBacktest,
  type BacktestRunOut,
} from "@/lib/api";

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86400_000).toISOString();
}

function EquityCurve({ curve, initial }: { curve: number[]; initial: number }) {
  if (curve.length < 2) return null;
  const w = 600;
  const h = 140;
  const min = Math.min(...curve, initial);
  const max = Math.max(...curve, initial);
  const range = max - min || 1;
  const pts = curve.map(
    (v, i) =>
      `${((i / (curve.length - 1)) * w).toFixed(1)},${(h - ((v - min) / range) * (h - 10) - 5).toFixed(1)}`,
  );
  const final = curve[curve.length - 1];
  const up = final >= initial;
  const color = up ? "#10b981" : "#f43f5e";
  const baselineY = h - ((initial - min) / range) * (h - 10) - 5;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-36" preserveAspectRatio="none">
      <defs>
        <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* initial balance baseline */}
      <line x1="0" y1={baselineY} x2={w} y2={baselineY} stroke="#243044" strokeDasharray="4 3" strokeWidth="1" />
      <polygon points={`0,${baselineY} ${pts.join(" ")} ${w},${baselineY}`} fill="url(#eq-fill)" />
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

const METRIC_LABELS: [string, string, (v: number) => string][] = [
  ["total_return", "TOTAL RETURN", (v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`],
  ["win_rate", "WIN RATE", (v) => `${(v * 100).toFixed(1)}%`],
  ["profit_factor", "PROFIT FACTOR", (v) => v.toFixed(2)],
  ["sharpe_ratio", "SHARPE", (v) => v.toFixed(2)],
  ["sortino_ratio", "SORTINO", (v) => v.toFixed(2)],
  ["max_drawdown", "MAX DRAWDOWN", (v) => `${(v * 100).toFixed(2)}%`],
  ["expectancy", "EXPECTANCY", (v) => `$${v.toFixed(2)}`],
  ["total_trades", "TRADES", (v) => String(Math.round(v))],
  ["calmar_ratio", "CALMAR", (v) => v.toFixed(2)],
  ["annualized_return", "ANN. RETURN", (v) => `${(v * 100).toFixed(1)}%`],
  ["largest_win", "LARGEST WIN", (v) => `$${v.toFixed(2)}`],
  ["largest_loss", "LARGEST LOSS", (v) => `$${v.toFixed(2)}`],
];

export default function StrategyLabPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [startDate, setStartDate] = useState(() => isoDaysAgo(90).slice(0, 10));
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [balance, setBalance] = useState("10000");
  const [slPct, setSlPct] = useState("2");
  const [tpPct, setTpPct] = useState("4");
  const [commission, setCommission] = useState("0.1");
  const [lookback, setLookback] = useState("50");

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestRunOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<BacktestRunOut[]>([]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  async function refreshRuns() {
    try {
      setRuns(await listBacktests(undefined, 20));
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (user) refreshRuns();
  }, [user]);

  async function onRun() {
    setRunning(true);
    setError(null);
    try {
      const r = await runBacktest({
        symbol,
        timeframe,
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate + "T23:59:59").toISOString(),
        initial_balance: Number(balance),
        stop_loss_pct: Number(slPct),
        take_profit_pct: Number(tpPct),
        commission_pct: Number(commission),
        lookback: Number(lookback),
      });
      setResult(r);
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "backtest failed");
    } finally {
      setRunning(false);
    }
  }

  async function onDelete(id: number) {
    if (!confirm(`Delete backtest #${id}?`)) return;
    await deleteBacktest(id);
    if (result?.id === id) setResult(null);
    await refreshRuns();
  }

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const m = result?.metrics ?? {};
  const finalBal = result?.final_balance ?? result?.initial_balance ?? 0;
  const retPct = result ? ((finalBal - result.initial_balance) / result.initial_balance) * 100 : 0;

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <FlaskConical className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Strategy Lab</span>
        <span className="text-[9px] font-mono text-muted">BACKTEST ENGINE / MOMENTUM SIGNAL v1</span>
      </header>

      <div className="flex-1 min-h-0 flex">
        {/* Config rail */}
        <aside className="w-[260px] shrink-0 border-r border-border bg-panel overflow-y-auto p-3 flex flex-col gap-3">
          <div className="terminal-label">Parameters</div>
          {(
            [
              ["Symbol", symbol, setSymbol, "text"],
              ["Timeframe", timeframe, setTimeframe, "tf"],
              ["Start", startDate, setStartDate, "date"],
              ["End", endDate, setEndDate, "date"],
              ["Balance $", balance, setBalance, "number"],
              ["Stop Loss %", slPct, setSlPct, "number"],
              ["Take Profit %", tpPct, setTpPct, "number"],
              ["Commission %", commission, setCommission, "number"],
              ["Lookback", lookback, setLookback, "number"],
            ] as [string, string, (v: string) => void, string][]
          ).map(([label, val, set, type]) => (
            <label key={label} className="flex flex-col gap-1">
              <span className="text-[9px] font-mono text-muted uppercase">{label}</span>
              {type === "tf" ? (
                <select
                  value={val}
                  onChange={(e) => set(e.target.value)}
                  className="bg-bg border border-border px-2 py-1.5 text-xs font-mono text-primary"
                >
                  {["15m", "1h", "4h", "1d"].map((tf) => (
                    <option key={tf} value={tf}>{tf}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={type}
                  value={val}
                  onChange={(e) => set(e.target.value)}
                  className="bg-bg border border-border px-2 py-1.5 text-xs font-mono text-primary"
                />
              )}
            </label>
          ))}
          <button
            onClick={onRun}
            disabled={running}
            className="h-8 mt-1 border border-info text-info hover:bg-info/10 disabled:opacity-50 font-mono text-[10px] flex items-center justify-center gap-2"
          >
            <Play className="w-3 h-3" />
            {running ? "RUNNING…" : "RUN BACKTEST"}
          </button>
          {error && (
            <p className="text-[9px] font-mono text-bearish leading-relaxed">{error}</p>
          )}
          <p className="text-[8px] font-mono text-muted leading-relaxed mt-auto">
            REQUIRES STORED CANDLES IN DB. SIGNAL: MOMENTUM ±1% OVER LOOKBACK WINDOW. WALK-FORWARD + CUSTOM SIGNALS ON ROADMAP.
          </p>
        </aside>

        {/* Results */}
        <main className="flex-1 min-w-0 overflow-y-auto p-4 flex flex-col gap-4">
          {result && result.status === "COMPLETED" && (
            <>
              {/* Headline */}
              <div className="flex items-end gap-6">
                <div>
                  <div className="terminal-label mb-1">Final Balance</div>
                  <div className={`font-mono text-3xl font-bold ${retPct >= 0 ? "text-bullish" : "text-bearish"}`}>
                    ${finalBal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
                <div className={`font-mono text-lg ${retPct >= 0 ? "text-bullish" : "text-bearish"}`}>
                  {retPct >= 0 ? "+" : ""}{retPct.toFixed(2)}%
                </div>
                <div className="text-[9px] font-mono text-muted">
                  {result.symbol} · {result.timeframe} · {result.start_date.slice(0, 10)} → {result.end_date.slice(0, 10)}
                </div>
              </div>

              {/* Equity curve */}
              <section className="border border-border bg-panel p-3">
                <span className="terminal-label">Equity Curve</span>
                <div className="mt-2">
                  <EquityCurve curve={result.equity_curve ?? []} initial={result.initial_balance} />
                </div>
              </section>

              {/* Metrics grid */}
              <div className="grid grid-cols-4 xl:grid-cols-6 gap-px bg-border border border-border">
                {METRIC_LABELS.map(([key, label, fmt]) => {
                  const v = m[key];
                  const num = typeof v === "number" ? v : null;
                  const isLoss = num != null && (key === "max_drawdown" || key === "largest_loss") && num !== 0;
                  return (
                    <div key={key} className="bg-panel px-3 py-2.5">
                      <div className="terminal-label mb-1">{label}</div>
                      <div className={`font-mono text-sm font-semibold ${isLoss ? "text-bearish" : "text-primary"}`}>
                        {num != null ? fmt(num) : "—"}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {result && result.status === "FAILED" && (
            <div className="border border-bearish/40 bg-bearish/10 p-4 text-bearish text-xs font-mono">
              BACKTEST FAILED: {JSON.stringify(result.metrics?.error ?? "unknown")}
            </div>
          )}

          {!result && !running && (
            <div className="flex-1 grid place-content-center justify-items-center gap-3 text-center">
              <FlaskConical className="w-10 h-10 text-muted/40" />
              <strong className="text-[11px] font-mono text-primary tracking-widest">NO BACKTEST LOADED</strong>
              <span className="text-[10px] text-muted">Configure parameters and run a backtest.</span>
            </div>
          )}

          {/* History */}
          <section>
            <span className="terminal-label">Run History</span>
            <div className="mt-2 border border-border bg-panel overflow-hidden">
              <table className="w-full text-[10px] font-mono">
                <thead className="bg-bg text-muted">
                  <tr>
                    {["#", "SYMBOL", "TF", "PERIOD", "RETURN", "STATUS", ""].map((h) => (
                      <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {runs.map((r) => {
                    const ret =
                      r.final_balance != null
                        ? ((r.final_balance - r.initial_balance) / r.initial_balance) * 100
                        : null;
                    return (
                      <tr
                        key={r.id}
                        onClick={() => setResult(r)}
                        className={`cursor-pointer transition-colors hover:bg-info/5 ${
                          result?.id === r.id ? "bg-info/10" : ""
                        }`}
                      >
                        <td className="px-3 py-2 text-muted">{r.id}</td>
                        <td className="px-3 py-2">{r.symbol}</td>
                        <td className="px-3 py-2">{r.timeframe}</td>
                        <td className="px-3 py-2 text-muted">{r.start_date.slice(0, 10)} → {r.end_date.slice(0, 10)}</td>
                        <td className={`px-3 py-2 ${ret != null ? (ret >= 0 ? "text-bullish" : "text-bearish") : "text-muted"}`}>
                          {ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%` : "—"}
                        </td>
                        <td className={`px-3 py-2 ${r.status === "COMPLETED" ? "text-bullish" : r.status === "FAILED" ? "text-bearish" : "text-amber-400"}`}>
                          {r.status}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={(e) => { e.stopPropagation(); onDelete(r.id); }}
                            className="text-muted hover:text-bearish p-1"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {runs.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-6 text-center text-muted">No backtests yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
