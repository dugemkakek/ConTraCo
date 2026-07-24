"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import type { Candle } from "@/lib/api";
import { request, getChartSignals, type TradeSignal } from "@/lib/api";

type Props = {
  symbol: string;
  venue: string;
  interval: string;
  height?: number;
  showSignals?: boolean;
};

const TF_MAP: Record<string, string> = {
  "1m": "1m", "5m": "5m", "15m": "15m",
  "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
};

function toUnixSeconds(iso: string | number) {
  const ms = typeof iso === "string" ? new Date(iso).getTime() : iso;
  return Math.floor(ms / 1000);
}

function symbolToApiPair(symbol: string): string {
  return symbol.replace("/", "").toUpperCase();
}

/**
 * TradingView Lightweight Chart wrapper.
 *
 * Chart library: TradingView's open-source Lightweight Charts (MIT).
 * Data source: this app's /market-data/{SYMBOL}/candles endpoint
 *   which fetches real public candles from Binance (with a free-tier
 *   CDN fallback) — no fabricated data ever.
 *
 * No API key is required for either the chart or the data feed.
 */
export function TradingViewChart({
  symbol,
  venue,
  interval,
  height = 520,
  showSignals = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<{
    candle: ISeriesApi<"Candlestick">;
    volume: ISeriesApi<"Histogram">;
    ema20: ISeriesApi<"Line">;
    ema50: ISeriesApi<"Line">;
    ema200: ISeriesApi<"Line">;
  } | null>(null);
  const lastKeyRef = useRef<string | null>(null);
  const priceLinesRef = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Chart lifetime owned by this single effect; cleanup nulls every ref.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: height || el.clientHeight || 400,
      layout: {
        background: { type: ColorType.Solid, color: "#0B0E14" },
        textColor: "#8B9BB4",
        fontFamily: '"JetBrains Mono", monospace',
      },
      grid: {
        vertLines: { color: "#1a2535" },
        horzLines: { color: "#1a2535" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        borderColor: "#1f2c3d",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#1f2c3d",
        scaleMargins: { top: 0.05, bottom: 0.2 },
      },
    });

    const candle = chart.addCandlestickSeries({
      upColor: "#10B981", downColor: "#F43F5E",
      borderUpColor: "#10B981", borderDownColor: "#F43F5E",
      wickUpColor: "#10B981", wickDownColor: "#F43F5E",
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "#1d2a3a",
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const ema20 = chart.addLineSeries({ color: "#00F0FF", lineWidth: 1, lineStyle: LineStyle.Solid, lastValueVisible: false, priceLineVisible: false });
    const ema50 = chart.addLineSeries({ color: "#F59E0B", lineWidth: 1, lineStyle: LineStyle.Solid, lastValueVisible: false, priceLineVisible: false });
    const ema200 = chart.addLineSeries({ color: "#A78BFA", lineWidth: 1, lineStyle: LineStyle.Dashed, lastValueVisible: false, priceLineVisible: false });

    seriesRef.current = { candle, volume, ema20, ema50, ema200 };
    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (chartRef.current && containerRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          ...(height === 0 ? { height: containerRef.current.clientHeight } : {}),
        });
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      try { chart.remove(); } catch { /* noop */ }
      chartRef.current = null;
      seriesRef.current = null;
      lastKeyRef.current = null;
    };
  }, [height]);

  // Data load keyed on (symbol, interval, venue).
  useEffect(() => {
    if (!seriesRef.current) return;
    const series = seriesRef.current;
    const apiPair = symbolToApiPair(symbol);
    const tf = TF_MAP[interval] || "1h";
    const dataKey = `${venue}:${apiPair}:${tf}`;

    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const url = `/api/v1/market-data/${apiPair}/candles?timeframe=${tf}&limit=500`;
        const response = await request<{
          candles: Candle[];
          data_freshness: string;
        }>(url);

        if (cancelled) return;
        if (!response.candles || response.candles.length === 0) {
          // Try graceful failover: if Binance pair is missing, try the
          // canonical CCXT-style symbol with separator.
          const fallback = await request<{ candles: Candle[] }>(
            `/api/v1/market-data/${symbol.toUpperCase()}/candles?timeframe=${tf}&limit=500`,
          );
          if (cancelled) return;
          if (!fallback.candles || fallback.candles.length === 0) {
            setError(`No real-time data available for ${symbol} on ${venue.toUpperCase()}.`);
            setLoading(false);
            return;
          }
          applySeries(fallback.candles, series, chartRef.current);
        } else {
          applySeries(response.candles, series, chartRef.current);
        }
        lastKeyRef.current = dataKey;
        setLoading(false);
      } catch (exc) {
        if (cancelled) return;
        setError(
          `Failed to reach market data: ${String((exc as Error).message ?? exc)}`,
        );
        setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [symbol, interval, venue]);

  // Signal overlay — markers + TP/SL price lines for the latest signal.
  useEffect(() => {
    if (!showSignals || !seriesRef.current) return;
    const series = seriesRef.current;
    const apiPair = symbolToApiPair(symbol);
    const tf = TF_MAP[interval] || "1h";
    let cancelled = false;

    (async () => {
      try {
        const res = await getChartSignals(apiPair, tf);
        if (cancelled || !seriesRef.current) return;
        const sigs = res.signals ?? [];

        // Markers on every signal bar
        const markers = sigs.map((s) => ({
          time: s.time as any,
          position: (s.side === "buy" ? "belowBar" : "aboveBar") as "belowBar" | "aboveBar",
          color: s.side === "buy" ? "#10B981" : "#F43F5E",
          shape: (s.side === "buy" ? "arrowUp" : "arrowDown") as "arrowUp" | "arrowDown",
          text: `${s.side.toUpperCase()} ${s.entry}`,
        }));
        series.candle.setMarkers(markers);

        // Price lines for the most recent signal
        priceLinesRef.current.forEach((pl) => {
          try { series.candle.removePriceLine(pl); } catch { /* noop */ }
        });
        priceLinesRef.current = [];

        const latest = sigs[sigs.length - 1];
        if (latest) {
          const addLine = (price: number, color: string, title: string, style: number) => {
            const pl = series.candle.createPriceLine({
              price, color, lineWidth: 1, lineStyle: style as any,
              axisLabelVisible: true, title,
            });
            priceLinesRef.current.push(pl);
          };
          addLine(latest.entry, "#8B9BB4", "ENTRY", 0);
          addLine(latest.stop_loss, "#F43F5E", "SL", 2);
          addLine(latest.take_profit_1, "#10B981", "TP1", 2);
          addLine(latest.take_profit_2, "#10B981", "TP2", 2);
        }
      } catch {
        // Signals are best-effort; chart still works without them.
      }
    })();

    return () => {
      cancelled = true;
      if (seriesRef.current) {
        seriesRef.current.candle.setMarkers([]);
        priceLinesRef.current.forEach((pl) => {
          try { seriesRef.current?.candle.removePriceLine(pl); } catch { /* noop */ }
        });
        priceLinesRef.current = [];
      }
    };
  }, [showSignals, symbol, interval]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />
      {loading && (
        <div className="absolute inset-x-0 top-2 flex items-center justify-center pointer-events-none">
          <span className="bg-panel/80 border border-border text-muted text-[10px] font-mono px-2 py-1 backdrop-blur">
            loading live {symbol.toUpperCase()} {interval} …
          </span>
        </div>
      )}
      {error && !loading && (
        <div className="absolute inset-x-0 bottom-3 mx-auto w-fit max-w-[80%] bg-panel/95 border border-bearish text-bearish text-[11px] font-mono px-3 py-2 backdrop-blur">
          {error}
        </div>
      )}
    </div>
  );
}

function applySeries(
  candles: Candle[],
  series: {
    candle: ISeriesApi<"Candlestick">;
    volume: ISeriesApi<"Histogram">;
    ema20: ISeriesApi<"Line">;
    ema50: ISeriesApi<"Line">;
    ema200: ISeriesApi<"Line">;
  },
  chart: IChartApi | null,
) {
  const candleData = candles.map((c) => ({
    time: toUnixSeconds(c.timestamp) as any,
    open: c.open, high: c.high, low: c.low, close: c.close,
  }));
  const volumeData = candles.map((c) => ({
    time: toUnixSeconds(c.timestamp) as any,
    value: c.volume,
    color: c.close >= c.open ? "rgba(16,185,129,0.4)" : "rgba(244,63,94,0.4)",
  }));
  const closes = candleData.map((c) => c.close);
  const ema20 = ema(closes, 20);
  const ema50 = ema(closes, 50);
  const ema200 = ema(closes, 200);
  const line = (vals: (number | null)[]) => candleData
    .map((c, i) => (vals[i] == null ? null : { time: c.time as any, value: vals[i] as number }))
    .filter(Boolean) as { time: any; value: number }[];

  series.candle.setData(candleData);
  series.volume.setData(volumeData);
  series.ema20.setData(line(ema20));
  series.ema50.setData(line(ema50));
  series.ema200.setData(line(ema200));
  if (chart) chart.timeScale().fitContent();
}

// EMA helper mirrors server `indicators.ema` so the chart overlays match.
function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length < period) return out;
  let prior = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = prior;
  for (let i = period; i < values.length; i++) {
    prior = values[i] * k + prior * (1 - k);
    out[i] = prior;
  }
  return out;
}
