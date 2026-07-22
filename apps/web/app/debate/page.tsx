"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Activity, Gavel, ScanLine } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { runAnalysis, listRuns, type RunOut } from "@/lib/api";
import { SymbolSearch } from "@/components/terminal/SymbolSearch";
import { TimeframeSelector } from "@/components/terminal/TimeframeSelector";
import { ConfluenceGauge } from "@/components/decision/ConfluenceGauge";
import { DebateChamber } from "@/components/decision/DebateChamber";
import { GateMatrix } from "@/components/decision/GateMatrix";

export default function DebatePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [run, setRun] = useState<RunOut | null>(null);
  const [debating, setDebating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<RunOut[]>([]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  // Load latest run for this symbol on mount / symbol change
  useEffect(() => {
    if (!user) return;
    listRuns(symbol, 5)
      .then((runs) => {
        setHistory(runs);
        if (runs.length > 0 && !run) setRun(runs[0]);
      })
      .catch(() => {});
  }, [user, symbol]);

  const convene = useCallback(async () => {
    setDebating(true);
    setError(null);
    try {
      const result = await runAnalysis({ symbol, timeframe, strategy: "balanced" });
      setRun(result);
      setHistory((h) => [result, ...h].slice(0, 5));
    } catch (err) {
      setError(err instanceof Error ? err.message : "council failed to convene");
    } finally {
      setDebating(false);
    }
  }, [symbol, timeframe]);

  if (loading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg">
        <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const decision = run?.decision ?? null;
  const opinions = run?.opinions ?? [];
  const confluence = decision?.confluence_result ?? null;

  return (
    <div className="h-[calc(100vh-2.75rem)] flex flex-col bg-bg overflow-hidden">
      {/* Control bar */}
      <header className="h-11 border-b border-border bg-panel flex items-center px-3 gap-2 shrink-0">
        <Gavel className="w-3.5 h-3.5 text-info" />
        <span className="terminal-label">Debate Chamber</span>
        <SymbolSearch onSelect={(sym) => { setSymbol(sym); setRun(null); }} />
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
        <button
          onClick={convene}
          disabled={debating}
          className="ml-auto h-7 px-3 text-[10px] border border-info text-info hover:bg-info/10 disabled:opacity-50 font-mono flex items-center gap-2"
        >
          {debating ? <Activity className="w-3 h-3 animate-pulse" /> : <ScanLine className="w-3 h-3" />}
          {debating ? "COUNCIL IN SESSION" : "CONVENE COUNCIL"}
        </button>
      </header>

      {error && (
        <div className="px-3 py-1.5 bg-bearish/10 border-b border-bearish/40 text-bearish text-[10px] font-mono">
          {error}
        </div>
      )}

      {!run ? (
        <div className="flex-1 grid place-content-center justify-items-center gap-3 text-center">
          <div className={`radar-sweep ${debating ? "radar-active" : ""}`} />
          <strong className="text-[11px] font-mono text-primary tracking-widest">
            {debating ? "COUNCIL DELIBERATING" : "NO SESSION ACTIVE"}
          </strong>
          <span className="text-[10px] text-muted max-w-xs">
            {debating
              ? `Running 14 gates + 6 council members on ${symbol} ${timeframe}…`
              : `Select a symbol and convene the council to see bull vs bear cases, gate verdicts, and the confluence score.`}
          </span>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto">
          {/* Verdict strip */}
          <div className="grid grid-cols-[auto_1fr] border-b border-border bg-panel">
            <ConfluenceGauge result={confluence} />
            <div className="flex flex-col justify-center gap-1.5 px-4 border-l border-border min-w-0">
              <div className="flex items-center gap-3">
                <span className="terminal-label">Verdict</span>
                <strong
                  className={`font-mono text-sm tracking-wide ${
                    decision?.final_state === "TRADE"
                      ? "text-bullish"
                      : decision?.final_state === "WAIT"
                      ? "text-amber-400"
                      : "text-muted"
                  }`}
                >
                  {decision?.final_state ?? "PENDING"}
                </strong>
                {confluence?.direction && (
                  <span className="font-mono text-xs text-primary">{confluence.direction}</span>
                )}
              </div>
              {decision?.reason && (
                <p className="text-[10px] text-muted leading-relaxed line-clamp-2">{decision.reason}</p>
              )}
              {confluence?.scenario && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] font-mono">
                  <span className="text-primary">
                    <span className="text-muted">PRIMARY / </span>
                    {confluence.scenario.primary}
                  </span>
                  <span className="text-muted">
                    ALT / {confluence.scenario.alternative}
                  </span>
                  <span className="text-bearish">
                    INVALIDATION / {confluence.scenario.invalidation}
                  </span>
                </div>
              )}
              <div className="flex gap-4 text-[9px] font-mono text-muted">
                <span>GATE {decision?.gate_score != null ? (decision.gate_score * 100).toFixed(0) : "—"}</span>
                <span>MODEL {decision?.model_score != null ? (decision.model_score * 100).toFixed(0) : "—"}</span>
                <span>COMPOSITE {decision?.composite_score != null ? (decision.composite_score * 100).toFixed(0) : "—"}</span>
                <span>AGREEMENT {decision?.model_agreement != null ? `${(decision.model_agreement * 100).toFixed(0)}%` : "—"}</span>
                <span>DATA {decision?.data_completeness != null ? `${(decision.data_completeness * 100).toFixed(0)}%` : "—"}</span>
              </div>
            </div>
          </div>

          {/* Debate + Gates */}
          <div className="grid grid-cols-[1fr_340px] min-h-[400px]">
            <DebateChamber opinions={opinions} decision={decision} />
            <div className="border-l border-border overflow-y-auto">
              {run && <GateMatrix run={run} />}
              {/* Kelly sizing */}
              {confluence?.kelly && (
                <section className="p-3 border-b border-border">
                  <span className="terminal-label">Kelly Sizing</span>
                  <div className="grid grid-cols-2 gap-px bg-border mt-2">
                    {[
                      ["WIN PROB", confluence.kelly.win_probability != null ? `${(confluence.kelly.win_probability * 100).toFixed(0)}%` : "—"],
                      ["W/L RATIO", confluence.kelly.win_loss_ratio != null ? confluence.kelly.win_loss_ratio.toFixed(2) : "—"],
                      ["FULL KELLY", confluence.kelly.full_kelly != null ? `${(confluence.kelly.full_kelly * 100).toFixed(1)}%` : "—"],
                      ["HALF KELLY", confluence.kelly.half_kelly != null ? `${(confluence.kelly.half_kelly * 100).toFixed(1)}%` : "—"],
                      ["QUARTER", confluence.kelly.quarter_kelly != null ? `${(confluence.kelly.quarter_kelly * 100).toFixed(1)}%` : "—"],
                      ["ACTIONABLE", confluence.is_actionable ? "YES" : "NO"],
                    ].map(([k, v]) => (
                      <div key={k} className="bg-panel px-2 py-1.5">
                        <div className="terminal-label">{k}</div>
                        <div className="font-mono text-xs text-primary">{v}</div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {/* Recent sessions */}
              <section className="p-3">
                <span className="terminal-label">Recent Sessions</span>
                <div className="flex flex-col gap-1 mt-2">
                  {history.map((h) => (
                    <button
                      key={h.id}
                      onClick={() => setRun(h)}
                      className={`text-left px-2 py-1.5 border text-[9px] font-mono flex items-center gap-2 transition-colors ${
                        h.id === run.id
                          ? "border-info/50 bg-info/10 text-info"
                          : "border-border text-muted hover:text-primary hover:border-info/30"
                      }`}
                    >
                      <span>#{h.id}</span>
                      <span>{h.symbol}</span>
                      <span>{h.timeframe}</span>
                      <span className="ml-auto">{h.final_state ?? "—"}</span>
                      <span className="text-muted">
                        {new Date(h.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
