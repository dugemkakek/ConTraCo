/** Inline SVG sparkline — no dependencies, ~20 lines. */

type Props = {
  data: number[];
  width?: number;
  height?: number;
  upColor?: string;
  downColor?: string;
};

export function Sparkline({
  data,
  width = 96,
  height = 28,
  upColor = "#22C55E",
  downColor = "#EF4444",
}: Props) {
  if (data.length < 2) return null;
  const mn = Math.min(...data);
  const mx = Math.max(...data);
  const range = mx - mn || 1;
  const xs = data.map((_, i) => (i / (data.length - 1)) * width);
  const ys = data.map((v) => height - ((v - mn) / range) * (height - 2) - 1);
  const d = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const color = data[0] <= data[data.length - 1] ? upColor : downColor;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="shrink-0"
    >
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
