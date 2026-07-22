"use client";

import type { ConfluenceResult } from "@/lib/api";

const BAND_COLOR: Record<ConfluenceResult["band"], string> = {
  STRONG: "#10B981",
  MODERATE: "#00F0FF",
  WEAK: "#F59E0B",
  DIVERGENT: "#64748B",
};

export function ConfluenceGauge({ result }: { result: ConfluenceResult | null | undefined }) {
  const score = Math.max(0, Math.min(100, result?.score ?? 0));
  const color = result ? BAND_COLOR[result.band] : "#334155";
  const circumference = 2 * Math.PI * 46;
  const dash = circumference * (score / 100);

  return (
    <section className="confluence-gauge" aria-label={`Confluence ${score.toFixed(0)} percent`}>
      <div className="gauge-ring">
        <svg viewBox="0 0 108 108" role="img" aria-hidden="true">
          <circle className="gauge-track" cx="54" cy="54" r="46" />
          <circle
            className="gauge-value"
            cx="54"
            cy="54"
            r="46"
            style={{ stroke: color, strokeDasharray: `${dash} ${circumference - dash}` }}
          />
        </svg>
        <div className="gauge-copy">
          <strong style={{ color }}>{score.toFixed(0)}</strong>
          <span>/ 100</span>
        </div>
      </div>
      <div className="gauge-meta">
        <span className="terminal-label">Confluence</span>
        <strong style={{ color }}>{result?.band ?? "AWAITING"}</strong>
        <span>{result?.direction ?? "NO SIGNAL"}</span>
        {result?.regime && <small>REGIME / {result.regime}</small>}
      </div>
    </section>
  );
}
