"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  getScanStatus,
  listLatestScans,
  startScan,
  type ScanResult,
  type ScanStatus,
} from "@/lib/api";

const STATE_COLOR: Record<string, string> = {
  LONG_CANDIDATE: "text-bullish",
  SHORT_CANDIDATE: "text-bearish",
  AVOID: "text-bearish",
  WAIT: "text-warning",
  DATA_INVALID: "text-neutral",
};

export default function ScanPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [latest, setLatest] = useState<ScanResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const s = await getScanStatus();
        const l = await listLatestScans(20);
        if (!active) return;
        setStatus(s);
        setLatest(l);
      } catch {
        // ignore
      }
    }
    refresh();
    const t = setInterval(refresh, 1500);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [user]);

  async function onScan() {
    setBusy(true);
    setError(null);
    try {
      const s = await startScan({ timeframe: "1h", strategy: "balanced", candle_limit: 200 });
      setStatus(s);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "scan failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="p-6 max-w-6xl mx-auto flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Scanner</h1>
        <button
          onClick={onScan}
          disabled={busy || status?.running}
          className="px-3 py-1.5 text-xs rounded-md border border-info text-info hover:bg-info/20 disabled:opacity-50"
        >
          {status?.running
            ? `Scanning ${status.completed}/${status.total}…`
            : "Run universe scan"}
        </button>
      </header>

      {error && <p className="text-bearish text-sm">{error}</p>}

      {status && status.running && (
        <div className="rounded-md border border-border bg-panel p-3 text-xs">
          <div className="flex items-center justify-between mb-2">
            <span>
              Scanning {status.completed}/{status.total}
              {status.current ? ` — current: ${status.current}` : ""}
            </span>
            <span className="text-muted">{Math.round((status.completed / status.total) * 100)}%</span>
          </div>
          <div className="h-1 bg-bg rounded">
            <div
              className="h-1 bg-info rounded"
              style={{ width: `${(status.completed / status.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      <section>
        <h2 className="text-sm font-semibold text-muted uppercase mb-2">
          Notable on this run
        </h2>
        {status?.notable.length ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {status.notable.slice().reverse().map((r) => (
              <Link
                key={r.run_id}
                href={`/terminal/${r.symbol.replace("/", "-")}`}
                className={`rounded-md border border-border bg-panel p-2 text-xs hover:border-info ${
                  STATE_COLOR[r.final_state ?? ""] ?? ""
                }`}
              >
                <div className="font-semibold">{r.symbol}</div>
                <div>{r.final_state}</div>
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted">No notable candidates yet.</p>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-muted uppercase mb-2">
          Latest per symbol
        </h2>
        <div className="rounded-md border border-border bg-panel divide-y divide-border text-xs">
          {latest.map((r) => (
            <Link
              key={`${r.symbol}-${r.run_id}`}
              href={`/terminal/${r.symbol.replace("/", "-")}`}
              className="flex items-center justify-between px-3 py-2 hover:bg-border/40"
            >
              <span className="font-medium">{r.symbol}</span>
              <span className={STATE_COLOR[r.final_state ?? ""] ?? "text-muted"}>
                {r.final_state ?? "—"}
              </span>
              <span className="text-muted">{r.timeframe}</span>
              <span className="text-muted">{new Date(r.started_at).toLocaleString()}</span>
            </Link>
          ))}
          {latest.length === 0 && (
            <p className="text-muted p-3">No scans yet.</p>
          )}
        </div>
      </section>
    </main>
  );
}
