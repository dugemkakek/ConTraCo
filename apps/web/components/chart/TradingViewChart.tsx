"use client";

import { useEffect, useRef } from "react";

type Props = {
  symbol: string;
  venue: string;
  interval: string;
  onSymbolChange?: (symbol: string, venue: string) => void;
  height?: number;
};

const VENUE_TO_TV_PREFIX: Record<string, string> = {
  gateio: "GATEIO",
  binance: "BINANCE",
  mock: "GATEIO",
};

const TF_TO_TV_INTERVAL: Record<string, string> = {
  "1m": "1",
  "5m": "5",
  "15m": "15",
  "1h": "60",
  "4h": "240",
  "1d": "D",
};

export function TradingViewChart({
  symbol,
  venue,
  interval,
  onSymbolChange,
  height = 520,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);
  const containerId = `tv-chart-${symbol.replace("/", "-").toLowerCase()}-${Math.random().toString(36).slice(2, 6)}`;

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;

    // Load TradingView script if not in DOM
    const scriptId = "tradingview-widget-script";
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;
    const scriptLoadPromise = new Promise<void>((resolve) => {
      if ((window as any).TradingView) {
        resolve();
        return;
      }
      if (!script) {
        script = document.createElement("script");
        script.id = scriptId;
        script.src = "https://s3.tradingview.com/tv.js";
        script.async = true;
        script.onload = () => resolve();
        document.body.appendChild(script);
      } else {
        // script exists but not yet loaded
        script.onload = () => resolve();
      }
    });

    scriptLoadPromise.then(() => {
      if (!el || !(window as any).TradingView) return;

      // Remove old widget if it exists
      if (widgetRef.current) {
        try { widgetRef.current.remove(); } catch { /* ignore */ }
        widgetRef.current = null;
      }

      const prefix = VENUE_TO_TV_PREFIX[venue] || "GATEIO";
      const tvSymbol = `${prefix}:${symbol.replace("/", "")}`;
      const tvInterval = TF_TO_TV_INTERVAL[interval] || "60";

      const widget = new (window as any).TradingView.widget({
        container_id: el.id,
        autosize: true,
        symbol: tvSymbol,
        interval: tvInterval,
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        toolbar_bg: "#0B0F14",
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        studies: ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"],
        show_popup_button: true,
        popup_width: "1000",
        popup_height: "650",
        overrides: {
          "paneProperties.background": "#0B0F14",
          "paneProperties.vertGridProperties.color": "#1a2535",
          "paneProperties.horzGridProperties.color": "#1a2535",
        },
      });

      widgetRef.current = widget;
    });

    return () => {
      if (widgetRef.current) {
        try { widgetRef.current.remove(); } catch { /* ignore */ }
        widgetRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, venue, interval]);

  return (
    <div
      id={containerId}
      ref={containerRef}
      className="w-full"
      style={{ height }}
    />
  );
}
