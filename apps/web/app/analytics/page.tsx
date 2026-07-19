"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { request } from "@/lib/api";

export default function AnalyticsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data: overview } = useQuery({
    queryKey: ["analytics-overview"],
    queryFn: () => request<any>("/api/v1/analytics/overview"),
    enabled: !!user,
  });

  const { data: equity } = useQuery({
    queryKey: ["analytics-equity"],
    queryFn: () => request<any>("/api/v1/analytics/equity-curve"),
    enabled: !!user,
  });

  const { data: bySymbol } = useQuery({
    queryKey: ["analytics-symbol"],
    queryFn: () => request<any>("/api/v1/analytics/by-symbol"),
    enabled: !!user,
  });

  const { data: byHour } = useQuery({
    queryKey: ["analytics-hour"],
    queryFn: () => request<any>("/api/v1/analytics/by-hour"),
    enabled: !!user,
  });

  return (
    <main className="p-4 max-w-6xl mx-auto flex flex-col gap-4">
      <h1 className="text-lg font-semibold">Performance Analytics</h1>

      {/* Overview cards */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Total Trades" value={overview.total_trades} />
          <StatCard label="Win Rate" value={`${(overview.win_rate * 100).toFixed(1)}%`} />
          <StatCard label="Total PnL" value={`$${overview.total_pnl.toFixed(2)}`} color={overview.total_pnl >= 0 ? "text-bullish" : "text-bearish"} />
          <StatCard label="Profit Factor" value={overview.profit_factor.toFixed(2)} />
          <StatCard label="Expectancy" value={`$${overview.expectancy.toFixed(2)}`} />
          <StatCard label="Sharpe" value={overview.sharpe_ratio.toFixed(2)} />
          <StatCard label="Max Drawdown" value={`${(overview.max_drawdown * 100).toFixed(1)}%`} color="text-bearish" />
          <StatCard label="Best/Worst" value={`$${overview.largest_win.toFixed(0)} / $${Math.abs(overview.largest_loss).toFixed(0)}`} />
        </div>
      )}

      {/* Equity curve */}
      {equity?.equity?.length > 1 && (
        <div className="bg-panel border border-border rounded-md p-3">
          <h3 className="text-xs font-semibold text-muted uppercase mb-2">Equity Curve</h3>
          <div className="h-32 flex items-end gap-[2px]">
            {equity.equity.map((v: number, i: number) => {
              const min = Math.min(...equity.equity);
              const max = Math.max(...equity.equity);
              const range = max - min || 1;
              const h = ((v - min) / range) * 100;
              return (
                <div
                  key={i}
                  className="flex-1 bg-info/60 hover:bg-info rounded-t"
                  style={{ height: `${h}%` }}
                  title={`$${v.toFixed(2)}`}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* By symbol */}
      {bySymbol?.symbols?.length > 0 && (
        <div className="bg-panel border border-border rounded-md p-3">
          <h3 className="text-xs font-semibold text-muted uppercase mb-2">By Symbol</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted border-b border-border">
                <th className="text-left py-1">Symbol</th>
                <th className="text-right py-1">Trades</th>
                <th className="text-right py-1">PnL</th>
                <th className="text-right py-1">Wins</th>
              </tr>
            </thead>
            <tbody>
              {bySymbol.symbols.map((s: any) => (
                <tr key={s.symbol} className="border-b border-border/40">
                  <td className="py-1 text-primary">{s.symbol}</td>
                  <td className="py-1 text-right text-muted">{s.trades}</td>
                  <td className={`py-1 text-right ${s.pnl >= 0 ? "text-bullish" : "text-bearish"}`}>
                    ${s.pnl.toFixed(2)}
                  </td>
                  <td className="py-1 text-right text-muted">{s.wins}/{s.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* By hour heatmap */}
      {byHour?.hourly && Object.keys(byHour.hourly).length > 0 && (
        <div className="bg-panel border border-border rounded-md p-3">
          <h3 className="text-xs font-semibold text-muted uppercase mb-2">Performance by Hour (UTC)</h3>
          <div className="flex gap-1 flex-wrap">
            {Array.from({ length: 24 }, (_, h) => {
              const pnl = byHour.hourly[h] ?? 0;
              const intensity = Math.min(Math.abs(pnl) / 10, 1);
              return (
                <div
                  key={h}
                  className="w-8 h-8 rounded flex items-center justify-center text-[10px]"
                  style={{
                    backgroundColor: pnl >= 0
                      ? `rgba(34, 197, 94, ${intensity})`
                      : `rgba(239, 68, 68, ${intensity})`,
                    color: intensity > 0.5 ? "white" : "#8B9BB4",
                  }}
                  title={`Hour ${h}: $${pnl.toFixed(2)}`}
                >
                  {h}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!overview && (
        <p className="text-muted text-sm">No trade data yet. Add journal entries to see analytics.</p>
      )}
    </main>
  );
}

function StatCard({ label, value, color = "text-primary" }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-panel border border-border rounded-md p-3">
      <div className="text-[10px] text-muted uppercase">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  );
}
