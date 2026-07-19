import type { RunOut } from "@/lib/api";

const DIRECTION_COLOR: Record<string, string> = {
  LONG: "text-bullish",
  SHORT: "text-bearish",
  WAIT: "text-warning",
  MISSING: "text-muted",
};

export function ModelOpinions({ run }: { run: RunOut }) {
  if (!run.opinions?.length) return null;

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-muted uppercase">Council Opinions</h4>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted border-b border-border">
            <th className="text-left py-1 pr-2">Role</th>
            <th className="text-left py-1 pr-2">Direction</th>
            <th className="text-right py-1 pr-2">Confidence</th>
            <th className="text-left py-1">Reason</th>
          </tr>
        </thead>
        <tbody>
          {run.opinions.map((o, i) => (
            <tr key={i} className="border-b border-border/40">
              <td className="py-1 pr-2 text-primary whitespace-nowrap">{o.role}</td>
              <td className={`py-1 pr-2 font-medium ${DIRECTION_COLOR[o.direction] ?? "text-muted"}`}>
                {o.direction}
              </td>
              <td className="py-1 pr-2 text-right text-muted">
                {(o.confidence * 100).toFixed(0)}%
              </td>
              <td className="py-1 text-muted truncate max-w-[160px]">{o.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
