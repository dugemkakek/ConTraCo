"use client";

import type { RunOut } from "@/lib/api";

const STATE_COLOR: Record<string, string> = {
  LONG_CANDIDATE: "bg-bullish/20 border-bullish text-bullish",
  SHORT_CANDIDATE: "bg-bearish/20 border-bearish text-bearish",
  WAIT: "bg-warning/20 border-warning text-warning",
  AVOID: "bg-bearish/30 border-bearish text-bearish",
  DATA_INVALID: "bg-neutral/20 border-neutral text-neutral",
};

const STATUS_COLOR: Record<string, string> = {
  PASS: "text-bullish",
  FAIL: "text-bearish",
  NEUTRAL: "text-warning",
  VETO: "text-bearish font-bold",
  UNAVAILABLE: "text-neutral",
  VALID: "text-bullish",
  INVALID: "text-bearish",
  MISSING: "text-neutral",
};

export function DecisionConsole({ run }: { run: RunOut }) {
  const stateColor = STATE_COLOR[run.final_state ?? "WAIT"] ?? STATE_COLOR.WAIT;
  const decision = run.decision;

  return (
    <div
      data-testid="decision-console"
      className="flex flex-col gap-3 p-4 rounded-md bg-panel border border-border"
    >
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-primary">Decision</h2>
        <div className="text-xs text-muted">run #{run.id}</div>
      </header>

      <div
        data-testid="final-state"
        className={`flex flex-col gap-1 p-3 rounded border text-sm ${stateColor}`}
      >
        <div className="flex items-baseline justify-between">
          <span className="font-semibold text-base">
            {run.final_state ?? run.status}
          </span>
          {decision && (
            <span className="font-mono">
              {decision.composite_score >= 0 ? "+" : ""}
              {decision.composite_score.toFixed(1)}
            </span>
          )}
        </div>
        {decision && (
          <div className="text-[11px] opacity-80">{decision.reason}</div>
        )}
      </div>

      {decision && (
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          <Stat label="Gate" value={decision.gate_score} />
          <Stat label="Model" value={decision.model_score} />
          <Stat label="Agree" value={decision.model_agreement * 100} suffix="%" />
        </div>
      )}

      {decision && decision.vetoes.length > 0 && (
        <details className="text-[11px]" open>
          <summary className="cursor-pointer text-bearish">
            {decision.vetoes.length} veto(s)
          </summary>
          <ul className="list-disc list-inside space-y-1 text-muted mt-1">
            {decision.vetoes.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        </details>
      )}

      <section>
        <h3 className="text-xs font-semibold text-muted uppercase mb-1">Gates</h3>
        <div className="flex flex-col gap-1 text-[11px]">
          {run.gates.map((g) => (
            <div
              key={g.name}
              data-testid={`gate-${g.name}`}
              className="grid grid-cols-12 gap-2 items-baseline"
            >
              <span className="col-span-5 truncate">{g.name}</span>
              <span className={`col-span-2 ${STATUS_COLOR[g.status] ?? ""}`}>
                {g.status}
              </span>
              <span className="col-span-3 font-mono text-right">
                {g.score.toFixed(1)}
              </span>
              <span className="col-span-2 font-mono text-right text-muted">
                ×{(g.weight * 100).toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-xs font-semibold text-muted uppercase mb-1">
          Council ({run.opinions.length})
        </h3>
        <div className="flex flex-col gap-1 text-[11px]">
          {run.opinions.map((o) => (
            <div
              key={o.role}
              data-testid={`opinion-${o.role}`}
              className="grid grid-cols-12 gap-2 items-baseline"
            >
              <span className="col-span-6 truncate">{o.role}</span>
              <span
                className={`col-span-3 ${STATUS_COLOR[o.status] ?? ""}`}
              >
                {o.direction}
              </span>
              <span className="col-span-3 font-mono text-right text-muted">
                {(o.confidence * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number;
  suffix?: string;
}) {
  const display = suffix === "%" ? `${value.toFixed(0)}%` : value.toFixed(1);
  return (
    <div className="rounded bg-bg border border-border px-2 py-1 text-center">
      <div className="text-muted">{label}</div>
      <div className="font-mono text-primary">{display}</div>
    </div>
  );
}
