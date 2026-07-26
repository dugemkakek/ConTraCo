"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  closeJournalEntry,
  createJournalEntry,
  deleteJournalEntry,
  journalSummary,
  listJournal,
  secContext,
  type JournalEntry,
  type SecCompanyContext,
  type SecFinancialPoint,
} from "@/lib/api";

export default function JournalPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [summary, setSummary] = useState<{
    total_entries: number;
    open_entries: number;
    closed_entries: number;
    total_pnl: number;
    winners: number;
    losers: number;
  } | null>(null);

  const [symbol, setSymbol] = useState("BTC/USDT");
  const [side, setSide] = useState<"LONG" | "SHORT">("LONG");
  const [entryPrice, setEntryPrice] = useState("");
  const [qty, setQty] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  async function refresh() {
    try {
      const [e, s] = await Promise.all([listJournal(), journalSummary()]);
      setEntries(e);
      setSummary(s);
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (user) refresh();
  }, [user]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createJournalEntry({
        symbol,
        side,
        entry_price: Number(entryPrice),
        qty: Number(qty),
        opened_at: new Date().toISOString(),
        notes,
      });
      setEntryPrice("");
      setQty("");
      setNotes("");
      await refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "create failed");
    }
  }

  async function onClose(entry: JournalEntry, exitPrice: number) {
    try {
      await closeJournalEntry(entry.id, exitPrice);
      await refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "close failed");
    }
  }

  async function onDelete(entry: JournalEntry) {
    if (!confirm(`Delete entry #${entry.id}?`)) return;
    try {
      await deleteJournalEntry(entry.id);
      await refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "delete failed");
    }
  }

  return (
    <main className="p-6 max-w-6xl mx-auto flex flex-col gap-4">
      <header>
        <h1 className="text-lg font-semibold">Journal</h1>
      </header>

      {summary && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
          <Stat label="Open" value={summary.open_entries} />
          <Stat label="Closed" value={summary.closed_entries} />
          <Stat
            label="Total PnL"
            value={`$${summary.total_pnl.toFixed(2)}`}
            accent={summary.total_pnl >= 0 ? "bullish" : "bearish"}
          />
          <Stat label="Winners" value={summary.winners} accent="bullish" />
          <Stat label="Losers" value={summary.losers} accent="bearish" />
          <Stat label="Total" value={summary.total_entries} />
        </div>
      )}

      <SecFundamentalsPanel />

      <form
        onSubmit={onCreate}
        className="rounded-md border border-border bg-panel p-3 grid grid-cols-2 md:grid-cols-6 gap-2 text-xs items-end"
      >
        <Field label="Symbol">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-bg border border-border rounded px-2 py-1 text-primary"
          />
        </Field>
        <Field label="Side">
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as "LONG" | "SHORT")}
            className="w-full bg-bg border border-border rounded px-2 py-1 text-primary"
          >
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </Field>
        <Field label="Entry $">
          <input
            value={entryPrice}
            onChange={(e) => setEntryPrice(e.target.value)}
            type="number"
            step="0.01"
            required
            className="w-full bg-bg border border-border rounded px-2 py-1 text-primary"
          />
        </Field>
        <Field label="Qty">
          <input
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            type="number"
            step="0.0001"
            required
            className="w-full bg-bg border border-border rounded px-2 py-1 text-primary"
          />
        </Field>
        <Field label="Notes">
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full bg-bg border border-border rounded px-2 py-1 text-primary"
          />
        </Field>
        <button
          type="submit"
          className="px-3 py-1.5 rounded border border-info text-info hover:bg-info/20"
        >
          Add entry
        </button>
      </form>

      <div className="rounded-md border border-border bg-panel overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-bg text-muted">
            <tr>
              <th className="text-left px-3 py-2">Symbol</th>
              <th className="text-left px-3 py-2">Side</th>
              <th className="text-right px-3 py-2">Entry</th>
              <th className="text-right px-3 py-2">Exit</th>
              <th className="text-right px-3 py-2">Qty</th>
              <th className="text-right px-3 py-2">PnL</th>
              <th className="text-left px-3 py-2">Opened</th>
              <th className="text-left px-3 py-2">Closed</th>
              <th className="text-left px-3 py-2">Notes</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {entries.map((e) => {
              const pnl = e.pnl;
              const color =
                pnl == null
                  ? "text-muted"
                  : pnl >= 0
                  ? "text-bullish"
                  : "text-bearish";
              return (
                <tr key={e.id}>
                  <td className="px-3 py-2">{e.symbol}</td>
                  <td className="px-3 py-2">{e.side}</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {e.entry_price.toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {e.exit_price ? e.exit_price.toFixed(2) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{e.qty}</td>
                  <td className={`px-3 py-2 text-right font-mono ${color}`}>
                    {pnl == null ? "—" : `$${pnl.toFixed(2)}`}
                  </td>
                  <td className="px-3 py-2 text-muted">
                    {new Date(e.opened_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 text-muted">
                    {e.closed_at ? new Date(e.closed_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-3 py-2 text-muted truncate max-w-[200px]">
                    {e.notes}
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    {!e.closed_at && (
                      <button
                        onClick={() => {
                          const v = window.prompt("Exit price?", String(e.entry_price));
                          const n = v ? Number(v) : NaN;
                          if (!Number.isFinite(n)) return;
                          onClose(e, n);
                        }}
                        className="px-2 py-1 rounded border border-border text-muted hover:text-primary"
                      >
                        Close
                      </button>
                    )}
                    <button
                      onClick={() => onDelete(e)}
                      className="px-2 py-1 rounded border border-border text-muted hover:text-bearish"
                    >
                      Del
                    </button>
                  </td>
                </tr>
              );
            })}
            {entries.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-6 text-center text-muted">
                  No entries yet. Add one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: "bullish" | "bearish";
}) {
  const c =
    accent === "bullish"
      ? "text-bullish"
      : accent === "bearish"
      ? "text-bearish"
      : "text-primary";
  return (
    <div className="rounded border border-border bg-panel p-2">
      <div className="text-muted">{label}</div>
      <div className={`font-mono ${c}`}>{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-muted">
      <span>{label}</span>
      {children}
    </label>
  );
}

function SecFundamentalsPanel() {
  const [ticker, setTicker] = useState("AAPL");
  const [data, setData] = useState<SecCompanyContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onLookup(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setLoading(true);
    setError(null);
    try {
      setData(await secContext(t));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "lookup failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  const filings = data?.recent_filings ?? [];

  return (
    <section className="rounded-md border border-border bg-panel p-3 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
          SEC Fundamentals
        </h2>
        <span className="text-[10px] text-muted">
          source: sec_edgar · US-listed companies only
        </span>
      </div>
      <form onSubmit={onLookup} className="flex gap-2">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="Ticker (e.g. AAPL, MSFT)"
          className="w-48 bg-bg border border-border rounded px-2 py-1 text-xs text-primary"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-3 py-1 rounded border border-info text-info text-xs hover:bg-info/20 disabled:opacity-50"
        >
          {loading ? "Looking up…" : "Lookup"}
        </button>
      </form>
      {error && <p className="text-xs text-bearish">{error}</p>}
      {data && !data.available && (
        <p className="text-xs text-muted">
          {data.ticker}: {data.reason ?? "not available on SEC EDGAR"}
        </p>
      )}
      {data?.available && (
        <>
          <div>
            <div className="text-sm text-primary">{data.company_name}</div>
            <div className="text-[10px] text-muted font-mono">
              {data.ticker} · CIK {data.cik}
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <FinCell label="Revenue" point={data.financials?.revenue ?? null} kind="usd" />
            <FinCell label="Net income" point={data.financials?.net_income ?? null} kind="usd" />
            <FinCell label="EPS (diluted)" point={data.financials?.eps_diluted ?? null} kind="eps" />
            <FinCell label="Total assets" point={data.financials?.total_assets ?? null} kind="usd" />
          </div>
          {filings.length > 0 ? (
            <ul className="flex flex-col gap-1 text-xs">
              {filings.slice(0, 6).map((f, i) => (
                <li key={i} className="flex gap-2 items-baseline">
                  <span className="font-mono text-info shrink-0">{f.form}</span>
                  <span className="text-muted shrink-0">
                    {f.filing_date ? f.filing_date.slice(0, 10) : "—"}
                  </span>
                  <a
                    href={f.url}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate text-primary/80 underline decoration-border hover:text-primary"
                  >
                    {f.title || "filing"}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted">No recent 10-K/10-Q filings found.</p>
          )}
        </>
      )}
    </section>
  );
}

function FinCell({
  label,
  point,
  kind,
}: {
  label: string;
  point: SecFinancialPoint | null;
  kind: "usd" | "eps";
}) {
  const value =
    point?.value == null
      ? "—"
      : kind === "eps"
      ? `$${point.value.toFixed(2)}`
      : formatUsd(point.value);
  const sub = [point?.period, point?.form].filter(Boolean).join(" · ");
  return (
    <div className="rounded border border-border bg-bg p-2">
      <div className="text-muted">{label}</div>
      <div className="font-mono text-primary">{value}</div>
      <div className="text-[10px] text-muted">{sub || " "}</div>
    </div>
  );
}

function formatUsd(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(2)}`;
}
