"use client";

import { useState, useCallback } from "react";
import { X, Plus, Maximize2, Minimize2 } from "lucide-react";
import { TradingViewChart } from "./TradingViewChart";

export type ChartSlot = {
  id: string;
  symbol: string;
  venue: string;
  interval: string;
};

let _nextId = 1;

const DEFAULT_SLOTS: ChartSlot[] = [
  { id: "s1", symbol: "BTC/USDT", venue: "binance", interval: "1h" },
  { id: "s2", symbol: "ETH/USDT", venue: "binance", interval: "1h" },
];

/**
 * Multi-ticker chart grid. Each cell is an independent lightweight-charts
 * instance with its own data fetch. Supports add/remove/maximize.
 *
 * ponytail: crosshair sync across charts is the ceiling — add via
 * chart.timeScale().subscribeVisibleLogicalRangeChange() forwarding
 * when a user actually asks for it.
 */
export function MultiChartGrid({
  initialSlots,
}: {
  initialSlots?: ChartSlot[];
}) {
  const [slots, setSlots] = useState<ChartSlot[]>(
    initialSlots ?? DEFAULT_SLOTS,
  );
  const [maximized, setMaximized] = useState<string | null>(null);
  const [addSymbol, setAddSymbol] = useState("");

  const remove = useCallback((id: string) => {
    setSlots((prev) => prev.filter((s) => s.id !== id));
    setMaximized((m) => (m === id ? null : m));
  }, []);

  const add = useCallback(() => {
    const sym = addSymbol.trim().toUpperCase() || "SOL/USDT";
    const id = `s${_nextId++}`;
    setSlots((prev) => [
      ...prev,
      { id, symbol: sym, venue: "binance", interval: "1h" },
    ]);
    setAddSymbol("");
  }, [addSymbol]);

  const visible = maximized
    ? slots.filter((s) => s.id === maximized)
    : slots;

  const cols =
    visible.length <= 1
      ? "grid-cols-1"
      : visible.length <= 4
        ? "grid-cols-2"
        : "grid-cols-3";

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-border bg-panel shrink-0">
        <span className="terminal-label">
          {maximized ? "FOCUS" : `${slots.length} CHARTS`}
        </span>
        <div className="flex items-center gap-1 ml-auto">
          <input
            value={addSymbol}
            onChange={(e) => setAddSymbol(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="BTC/USDT"
            className="w-24 h-6 px-2 text-[10px] font-mono bg-bg border border-border text-primary placeholder:text-muted/50 focus:border-info focus:outline-none"
          />
          <button
            onClick={add}
            className="h-6 w-6 flex items-center justify-center text-muted hover:text-info border border-border hover:border-info transition-colors"
            title="Add chart"
          >
            <Plus className="w-3 h-3" />
          </button>
          {maximized && (
            <button
              onClick={() => setMaximized(null)}
              className="h-6 px-2 flex items-center gap-1 text-[9px] font-mono text-muted hover:text-primary border border-border hover:border-info transition-colors"
            >
              <Minimize2 className="w-3 h-3" /> GRID
            </button>
          )}
        </div>
      </div>

      {/* Grid */}
      <div className={`flex-1 min-h-0 grid ${cols} gap-px bg-border overflow-auto`}>
        {visible.map((slot) => (
          <div
            key={slot.id}
            className="relative bg-bg flex flex-col min-h-[280px]"
          >
            {/* Cell header */}
            <div className="flex items-center gap-1.5 px-2 py-1 border-b border-border/50 shrink-0">
              <span className="font-mono text-[10px] font-semibold text-primary">
                {slot.symbol}
              </span>
              <span className="font-mono text-[8px] text-muted">
                {slot.venue.toUpperCase()} · {slot.interval.toUpperCase()}
              </span>
              <div className="ml-auto flex items-center gap-0.5">
                {!maximized && (
                  <button
                    onClick={() => setMaximized(slot.id)}
                    className="p-0.5 text-muted hover:text-info transition-colors"
                    title="Focus"
                  >
                    <Maximize2 className="w-3 h-3" />
                  </button>
                )}
                <button
                  onClick={() => remove(slot.id)}
                  className="p-0.5 text-muted hover:text-bearish transition-colors"
                  title="Remove"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>
            {/* Chart fills remaining space */}
            <div className="flex-1 min-h-0">
              <TradingViewChart
                symbol={slot.symbol}
                venue={slot.venue}
                interval={slot.interval}
                height={0}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
