"use client";

import { useState } from "react";
import type { RunOut } from "@/lib/api";
import { getTradesConfig, placeOrder, type TradesConfig } from "@/lib/api";
import { useEffect } from "react";

export function TradePanel({ run }: { run: RunOut }) {
  const [config, setConfig] = useState<TradesConfig | null>(null);
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">("LIMIT");
  const [price, setPrice] = useState<string>("");
  const [qty, setQty] = useState<string>("0.01");
  const [submitting, setSubmitting] = useState(false);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    getTradesConfig().then(setConfig).catch(() => null);
  }, []);

  const plan = run.trade_plan;
  const actionable =
    run.final_state === "LONG_CANDIDATE" || run.final_state === "SHORT_CANDIDATE";

  if (!actionable || !plan) {
    return (
      <div className="rounded-md border border-border p-3 text-xs text-muted">
        No trade plan generated. Plan appears only on <code>LONG_CANDIDATE</code> / <code>SHORT_CANDIDATE</code>.
      </div>
    );
  }

  const side = plan.direction === "LONG" ? "BUY" : "SELL";
  const refPrice = plan.entry_price ?? Number(price || 0);

  async function onSubmit() {
    setSubmitting(true);
    setErrorMsg(null);
    setResultMsg(null);
    try {
      const entryPrice = plan?.entry_price ?? null;
      const orderPrice = orderType === "LIMIT" ? Number(price) : entryPrice;
      const r = await placeOrder({
        symbol: run.symbol,
        side,
        order_type: orderType,
        qty: Number(qty),
        price: orderPrice,
        analysis_run_id: run.id,
        auto_journal: true,
      });
      setResultMsg(`Submitted ${side} ${qty} ${run.symbol} @ ${orderType} → status=${r.status}, id=${r.exchange_order_id}`);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "order failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-md border border-border bg-panel p-3 flex flex-col gap-2 text-xs">
      <h2 className="text-sm font-semibold text-primary">
        Trade plan · {plan.direction}
      </h2>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Entry" value={plan.entry_price?.toFixed(2)} />
        <Field label="Stop" value={plan.stop_price?.toFixed(2)} />
        <Field label="Take profit" value={plan.take_profit?.toFixed(2)} />
        <Field label="R:R" value={plan.risk_reward?.toFixed(2)} />
        <Field
          label="Size"
          value={plan.position_size_pct ? `${plan.position_size_pct.toFixed(1)}%` : "—"}
        />
        <Field
          label="Conf"
          value={run.decision ? `${(run.decision.model_agreement * 100).toFixed(0)}%` : "—"}
        />
      </div>
      <p className="text-[11px] text-muted">{plan.risk_review}</p>

      <div className="border-t border-border pt-2 mt-1 flex flex-col gap-2">
        <p className="text-[11px] text-warning">
          {config?.live_trading
            ? "LIVE TRADING ON — orders go to Gate.io with signed requests."
            : "Paper mode — orders are recorded locally. Set LIVE_TRADING=1 and provide GATEIO_API_KEY/SECRET to enable real trades."}
          {config ? ` Max notional $${config.max_notional_usd.toFixed(0)}.` : null}
        </p>
        <div className="flex gap-2 items-center">
          <select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value as "MARKET" | "LIMIT")}
            className="bg-bg border border-border rounded px-2 py-1 text-primary"
          >
            <option value="MARKET">MARKET</option>
            <option value="LIMIT">LIMIT</option>
          </select>
          <input
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="qty"
            className="bg-bg border border-border rounded px-2 py-1 text-primary w-24"
          />
          {orderType === "LIMIT" && (
            <input
              value={price || String(refPrice ?? "")}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="price"
              className="bg-bg border border-border rounded px-2 py-1 text-primary w-28"
            />
          )}
          <button
            onClick={onSubmit}
            disabled={submitting || !Number(qty)}
            className={`px-3 py-1 rounded border ${
              side === "BUY"
                ? "border-bullish text-bullish hover:bg-bullish/20"
                : "border-bearish text-bearish hover:bg-bearish/20"
            } disabled:opacity-50`}
          >
            {submitting ? "Submitting…" : `${side}`}
          </button>
        </div>
        {resultMsg && (
          <p data-testid="order-result" className="text-bullish">{resultMsg}</p>
        )}
        {errorMsg && (
          <p className="text-bearish">{errorMsg}</p>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <div className="text-muted">{label}</div>
      <div className="font-mono text-primary">{value ?? "—"}</div>
    </div>
  );
}
