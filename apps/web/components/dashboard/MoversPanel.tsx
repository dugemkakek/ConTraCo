import Link from "next/link";
import type { MarketOverview } from "@/lib/api";

type Props = {
  movers: MarketOverview["movers"];
};

export function MoversPanel({ movers }: Props) {
  return (
    <div className="bg-panel border border-border rounded-md p-4 flex flex-col gap-3">
      <span className="text-xs text-muted uppercase tracking-wider">
        Movers (24h)
      </span>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] text-bullish uppercase font-semibold">
            Gainers
          </span>
          {movers.gainers.map((t) => (
            <Link
              key={t.symbol}
              href={`/terminal/${t.symbol.replace("/", "-")}`}
              className="flex items-center justify-between text-xs hover:bg-border/40 px-1.5 py-0.5 rounded"
            >
              <span className="text-primary">{t.symbol.replace("/USDT", "")}</span>
              <span className="text-bullish">
                +{t.change_24h_pct?.toFixed(1)}%
              </span>
            </Link>
          ))}
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] text-bearish uppercase font-semibold">
            Losers
          </span>
          {movers.losers.map((t) => (
            <Link
              key={t.symbol}
              href={`/terminal/${t.symbol.replace("/", "-")}`}
              className="flex items-center justify-between text-xs hover:bg-border/40 px-1.5 py-0.5 rounded"
            >
              <span className="text-primary">{t.symbol.replace("/USDT", "")}</span>
              <span className="text-bearish">
                {t.change_24h_pct?.toFixed(1)}%
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
