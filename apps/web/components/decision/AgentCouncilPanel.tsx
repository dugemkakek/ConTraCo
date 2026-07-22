"use client";

import type { RunOut } from "@/lib/api";
import { ConfluenceGauge } from "./ConfluenceGauge";
import { GateMatrix } from "./GateMatrix";
import { RiskFlags } from "./RiskFlags";

type Props = { run: RunOut | null; isAnalyzing: boolean };

export function AgentCouncilPanel({ run, isAnalyzing }: Props) {
  if (!run) {
    return (
      <div className="empty-terminal-state">
        <div className={`radar-sweep ${isAnalyzing ? "radar-active" : ""}`} />
        <strong>{isAnalyzing ? "COUNCIL DELIBERATING" : "COUNCIL STANDBY"}</strong>
        <span>{isAnalyzing ? "Evaluating market evidence" : "Run analysis to activate 14 deterministic gates"}</span>
      </div>
    );
  }

  const confluence = run.decision?.confluence_result;
  return (
    <div className="agent-council">
      <ConfluenceGauge result={confluence} />
      <GateMatrix run={run} />
      {run.decision && (
        <section className="scenario-card">
          <span className="terminal-label">CRO Scenario Frame</span>
          <p>{confluence?.scenario.primary ?? run.decision.reason}</p>
          {confluence?.scenario.alternative && <small>ALT / {confluence.scenario.alternative}</small>}
          {confluence?.scenario.invalidation && <small className="text-warning">INVALIDATION / {confluence.scenario.invalidation}</small>}
        </section>
      )}
      {(run.decision?.vetoes?.length ?? 0) > 0 && <RiskFlags run={run} />}
    </div>
  );
}
