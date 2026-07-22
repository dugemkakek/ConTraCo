"use client";

import type { DebateCamp, DecisionOut, OpinionOut } from "@/lib/api";

type Props = { opinions: OpinionOut[]; decision: DecisionOut | null };

const LABELS: Record<string, string> = {
  technical_analyst: "Technical",
  market_context_analyst: "Market Context",
  risk_reviewer: "Risk CRO",
  skeptical_reviewer: "Skeptic",
  trade_planner: "Planner",
  synthesis_reviewer: "Synthesis",
};

function opinionCamp(opinions: OpinionOut[], direction: "LONG" | "SHORT" | "WAIT"): DebateCamp {
  const members = opinions
    .filter((o) => direction === "WAIT" ? o.direction !== "LONG" && o.direction !== "SHORT" : o.direction === direction)
    .map((o) => ({
      name: o.role,
      confidence: o.confidence,
      weight: o.role_weight,
      reasoning: o.reason,
      low_conviction: o.confidence < 0.3,
      source: "council" as const,
    }));
  return { members, summary: `${members.length} council position(s).`, total_weight: members.reduce((sum, m) => sum + m.weight, 0) };
}

function Camp({ title, camp, tone }: { title: string; camp: DebateCamp; tone: "bull" | "bear" | "neutral" }) {
  return (
    <section className={`debate-camp debate-${tone}`}>
      <header>
        <span className="debate-signal" />
        <strong>{title}</strong>
        <span>{camp.members.length}</span>
      </header>
      <p className="camp-summary">{camp.summary}</p>
      <div className="debate-stack">
        {camp.members.map((member, index) => (
          <article key={`${member.name}-${index}`} className={member.low_conviction ? "low-conviction" : ""}>
            <div>
              <strong>{LABELS[member.name] ?? member.name.replaceAll("_", " ")}</strong>
              <span>{Math.round(member.confidence * 100)}%</span>
            </div>
            <p>{member.reasoning || "No reasoning supplied."}</p>
            <small>{member.source.toUpperCase()}{member.low_conviction ? " / LOW CONVICTION" : ""}</small>
          </article>
        ))}
        {!camp.members.length && <span className="empty-camp">No active case</span>}
      </div>
    </section>
  );
}

export function DebateChamber({ opinions, decision }: Props) {
  const debate = decision?.confluence_result?.debate;
  const bull = debate?.bull ?? opinionCamp(opinions, "LONG");
  const bear = debate?.bear ?? opinionCamp(opinions, "SHORT");
  const neutral = debate?.neutral ?? opinionCamp(opinions, "WAIT");
  const vetoes = decision?.vetoes ?? [];

  return (
    <div className="debate-chamber">
      <div className="debate-header">
        <div>
          <span className="terminal-label">Chief Risk Officer</span>
          <strong>Debate Chamber</strong>
        </div>
        <span className="debate-tally"><b>{bull.members.length}</b> / {bear.members.length} / {neutral.members.length}</span>
      </div>
      {vetoes.length > 0 && <div className="veto-strip">VETO ACTIVE / {vetoes.join(" / ")}</div>}
      {debate?.debate_summary && <p className="debate-summary">{debate.debate_summary}</p>}
      <div className="debate-columns">
        <Camp title="BULL CASE" camp={bull} tone="bull" />
        <Camp title="BEAR CASE" camp={bear} tone="bear" />
      </div>
      <Camp title="NEUTRAL / ABSTAIN" camp={neutral} tone="neutral" />
    </div>
  );
}
