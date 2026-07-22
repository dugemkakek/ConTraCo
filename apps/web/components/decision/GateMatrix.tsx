"use client";

import type { RunOut } from "@/lib/api";

function direction(score: number) {
  if (score > 5) return { label: "BULL", cls: "gate-bull" };
  if (score < -5) return { label: "BEAR", cls: "gate-bear" };
  return { label: "FLAT", cls: "gate-flat" };
}

export function GateMatrix({ run }: { run: RunOut }) {
  return (
    <section className="gate-matrix">
      <header>
        <span className="terminal-label">Gate Matrix</span>
        <span className="font-mono text-[9px] text-muted">{run.gates.length} NODES</span>
      </header>
      <div className="gate-grid">
        {run.gates.map((gate) => {
          const dir = direction(gate.score);
          const unavailable = gate.status === "UNAVAILABLE";
          return (
            <article key={gate.name} className={`gate-cell ${unavailable ? "gate-offline" : dir.cls}`} title={gate.reason}>
              <div className="gate-cell-top">
                <span className="gate-led" />
                <span>{unavailable ? "OFF" : dir.label}</span>
                <strong>{Math.round(gate.confidence * 100)}</strong>
              </div>
              <p>{gate.name.replaceAll("_", " ")}</p>
              <div className="gate-confidence"><i style={{ width: `${Math.max(0, Math.min(100, gate.confidence * 100))}%` }} /></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
