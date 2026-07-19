import type { RunOut } from "@/lib/api";

const GATE_THRESHOLDS = [
  { max: 0.3, color: "bg-bearish/30 text-bearish", label: "low" },
  { max: 0.6, color: "bg-warning/30 text-warning", label: "medium" },
  { max: 1.0, color: "bg-bullish/30 text-bullish", label: "high" },
];

export function GateScores({ run }: { run: RunOut }) {
  if (!run.gates?.length) return null;

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-muted uppercase">Gate Scores</h4>
      {run.gates.map((g) => {
        const threshold = GATE_THRESHOLDS.find((t) => g.score <= t.max) ?? GATE_THRESHOLDS[0];
        return (
          <div key={g.name} className="flex flex-col gap-0.5">
            <div className="flex justify-between text-xs">
              <span className="text-primary">{g.name}</span>
              <span className={threshold.color}>{g.score.toFixed(2)}</span>
            </div>
            <div className="h-1.5 bg-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${threshold.color.split(" ")[0]}`}
                style={{ width: `${g.score * 100}%` }}
              />
            </div>
            <span className="text-[10px] text-muted">{g.reason}</span>
          </div>
        );
      })}
    </div>
  );
}
