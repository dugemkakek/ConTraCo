type Props = {
  breadth: { up: number; down: number; flat: number };
};

export function BreadthGauge({ breadth }: Props) {
  const { up, down, flat } = breadth;
  const total = up + down + flat || 1;

  return (
    <div className="bg-panel border border-border rounded-md p-4 flex flex-col gap-3">
      <span className="text-xs text-muted uppercase tracking-wider">Breadth</span>

      <div className="flex h-6 w-full rounded-full overflow-hidden text-[11px] font-semibold">
        {up > 0 && (
          <div
            className="flex items-center justify-center bg-bullish/80"
            style={{ width: `${(up / total) * 100}%` }}
          >
            {up > 0 && (up / total) * 100 > 12 ? up : ""}
          </div>
        )}
        {flat > 0 && (
          <div
            className="flex items-center justify-center bg-neutral/50"
            style={{ width: `${(flat / total) * 100}%` }}
          >
            {flat > 0 && (flat / total) * 100 > 12 ? flat : ""}
          </div>
        )}
        {down > 0 && (
          <div
            className="flex items-center justify-center bg-bearish/80"
            style={{ width: `${(down / total) * 100}%` }}
          >
            {down > 0 && (down / total) * 100 > 12 ? down : ""}
          </div>
        )}
      </div>

      <div className="flex justify-between text-xs text-muted">
        <span className="text-bullish">{up} up</span>
        <span>{flat} flat</span>
        <span className="text-bearish">{down} down</span>
      </div>

      <p className="text-xs text-primary/70">
        {Math.round((up / total) * 100)}% of tracked markets trending up
      </p>
    </div>
  );
}
