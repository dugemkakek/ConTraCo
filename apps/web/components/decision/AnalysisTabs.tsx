"use client";

import { useState } from "react";
import type { RunOut } from "@/lib/api";
import { DecisionConsole } from "./DecisionConsole";
import { TradePlanDetail } from "./TradePlanDetail";
import { GateScores } from "./GateScores";
import { ModelOpinions } from "./ModelOpinions";
import { RiskFlags } from "./RiskFlags";
import { RunHistory } from "./RunHistory";

type Props = {
  run: RunOut | null;
  isAnalyzing: boolean;
  symbol: string;
  onSelectRun?: (runId: number) => void;
};

type Tab = "analysis" | "details" | "history";

export function AnalysisTabs({ run, isAnalyzing, symbol, onSelectRun }: Props) {
  const [tab, setTab] = useState<Tab>("analysis");

  const tabs: { id: Tab; label: string }[] = [
    { id: "analysis", label: "Analysis" },
    { id: "details", label: "Details" },
    { id: "history", label: "History" },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 text-xs py-2 font-medium ${
              tab === t.id
                ? "text-info border-b-2 border-info"
                : "text-muted hover:text-primary"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-3">
        {isAnalyzing && (
          <div className="flex items-center gap-2 text-xs text-muted py-4">
            <div className="w-3 h-3 border border-info border-t-transparent rounded-full animate-spin" />
            Analyzing…
          </div>
        )}

        {tab === "analysis" && (
          <div className="flex flex-col gap-3">
            {run ? (
              <>
                <DecisionConsole run={run} />
                <TradePlanDetail run={run} />
              </>
            ) : !isAnalyzing ? (
              <div
                data-testid="decision-console-empty"
                className="flex flex-col gap-2 text-xs text-muted p-4 rounded-md border border-border"
              >
                <p>
                  Click <span className="text-primary font-medium">Run Analysis</span> to evaluate
                  this market against the council + gates.
                </p>
                <p>
                  Final state, gate scores, model votes, and an optional trade plan will appear here.
                </p>
              </div>
            ) : null}
          </div>
        )}

        {tab === "details" && run && (
          <div className="flex flex-col gap-4">
            <GateScores run={run} />
            <ModelOpinions run={run} />
            <RiskFlags run={run} />
          </div>
        )}

        {tab === "details" && !run && !isAnalyzing && (
          <p className="text-xs text-muted">Run analysis first to see gate scores and model opinions.</p>
        )}

        {tab === "history" && (
          <RunHistory
            symbol={symbol}
            onSelectRun={(id) => onSelectRun?.(id)}
          />
        )}
      </div>
    </div>
  );
}
