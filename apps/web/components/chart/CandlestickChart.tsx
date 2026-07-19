"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
} from "lightweight-charts";
import type { Candle } from "@/lib/api";
import { computeEMA } from "@/lib/indicators";

function toUnixSeconds(iso: string) {
  return Math.floor(new Date(iso).getTime() / 1000);
}

export function CandlestickChart({
  candles,
  dataKey,
}: {
  candles: Candle[];
  /** Stable identifier for the current dataset (e.g. "BTC/USDT:1h").
   *  When this changes we know the candle array is a fresh series —
   *  not just an in-place update — and we bulk-setData. */
  dataKey?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<{
    candle: ISeriesApi<"Candlestick">;
    volume: ISeriesApi<"Histogram">;
    ema20: ISeriesApi<"Line">;
    ema50: ISeriesApi<"Line">;
    ema200: ISeriesApi<"Line">;
  } | null>(null);
  const lastTimeRef = useRef<number | null>(null);
  const dataKeyRef = useRef<string | null>(null);

  // ONE effect owns chart lifetime. On React 19 strict-mode double-mount
  // the cleanup destroys everything and nulls every ref, so the data
  // effect can never write into dead series. The reset of lastTimeRef
  // guarantees a bulk setData on the next data effect after remount.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "#0B0F14" },
        textColor: "#8B9BB4",
      },
      grid: {
        vertLines: { color: "#233044" },
        horzLines: { color: "#233044" },
      },
      rightPriceScale: { borderColor: "#233044" },
      timeScale: { borderColor: "#233044" },
      height: 480,
      width: el.clientWidth || 600,
    });
    chartRef.current = chart;

    const candle = chart.addCandlestickSeries({
      upColor: "#22C55E",
      downColor: "#EF4444",
      borderVisible: false,
      wickUpColor: "#22C55E",
      wickDownColor: "#EF4444",
    });
    const volume = chart.addHistogramSeries({
      color: "#38BDF8",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volume.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });
    const ema20 = chart.addLineSeries({ color: "#38BDF8", lineWidth: 1 });
    const ema50 = chart.addLineSeries({ color: "#F59E0B", lineWidth: 1 });
    const ema200 = chart.addLineSeries({ color: "#8B5CF6", lineWidth: 1 });
    seriesRef.current = { candle, volume, ema20, ema50, ema200 };
    lastTimeRef.current = null; // force bulk setData on next data effect

    const ro = new ResizeObserver(() => {
      if (chartRef.current && el.clientWidth > 0) {
        chartRef.current.applyOptions({ width: el.clientWidth });
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lastTimeRef.current = null;
      dataKeyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Data-only effect — depends on candles + dataKey. If the chart hasn't
  // mounted yet (first-paint race), it no-ops; the chart effect's reset
  // of lastTimeRef guarantees a bulk setData once both are ready.
  useEffect(() => {
    const s = seriesRef.current;
    const chart = chartRef.current;
    if (!s || !chart || candles.length === 0) return;

    if (dataKey !== undefined && dataKeyRef.current !== dataKey) {
      dataKeyRef.current = dataKey;
      lastTimeRef.current = null;
    }

    const ts = toUnixSeconds(candles[candles.length - 1].timestamp);
    const last = candles[candles.length - 1];

    if (lastTimeRef.current === null) {
      // Bulk setData — first load or new dataKey
      s.candle.setData(
        candles.map((c) => ({
          time: toUnixSeconds(c.timestamp) as any,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      );
      s.volume.setData(
        candles.map((c) => ({
          time: toUnixSeconds(c.timestamp) as any,
          value: c.volume,
          color: c.close >= c.open ? "#22C55E55" : "#EF444455",
        })),
      );
      const toLine = (vals: number[]) =>
        candles
          .map((c, i) => ({
            time: toUnixSeconds(c.timestamp) as any,
            value: vals[i],
          }))
          .filter((p) => Number.isFinite(p.value));
      s.ema20.setData(toLine(computeEMA(candles, 20)));
      s.ema50.setData(toLine(computeEMA(candles, 50)));
      s.ema200.setData(toLine(computeEMA(candles, 200)));
      lastTimeRef.current = ts;
      chart.timeScale().fitContent();
      return;
    }

    // Streaming update — modify the last bar or append a new one
    lastTimeRef.current = ts;
    s.candle.update({
      time: ts as any,
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
    });
    s.volume.update({
      time: ts as any,
      value: last.volume,
      color: last.close >= last.open ? "#22C55E55" : "#EF444455",
    });
    const e20 = computeEMA(candles, 20);
    const e50 = computeEMA(candles, 50);
    const e200 = computeEMA(candles, 200);
    s.ema20.update({ time: ts as any, value: e20[e20.length - 1] });
    s.ema50.update({ time: ts as any, value: e50[e50.length - 1] });
    s.ema200.update({ time: ts as any, value: e200[e200.length - 1] });
  }, [candles, dataKey]);

  return (
    <div
      ref={containerRef}
      data-testid="candlestick-chart"
      className="w-full"
    />
  );
}
