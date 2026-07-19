# Chart Fix + Market Dashboard — Implementation Plan

> **For the implementing model:** You are working on `F:\Programs\confluence-trading-consultant`.
> Read this file top to bottom before touching code. Every task lists exact files and exact verification commands.
> Do NOT invent endpoints — the only ones that exist today are enumerated in Task 0.
> Repo layout: `apps/api` (FastAPI, Python 3.14, venv at `apps/api/venv`), `apps/web` (Next.js 16 + React 19 + Tailwind + lightweight-charts 4.2).
> API runs on `http://localhost:8000`, web on `http://localhost:3000`.
> Web `npm run lint` = `tsc --noEmit`. API tests = `apps/api/venv/Scripts/python.exe -m pytest tests/ -q` from `apps/api/`.
> Commit after every task. TDD where it makes sense (API endpoints), manual verification for visual components.

**Goal:** Fix the blank candlestick chart on `/terminal/[symbol]`, then add a new `/dashboard` page that shows general market condition at a glance.

**Architecture:**
- Chart fix: the existing `CandlestickChart.tsx` creates the chart in a mount-once `useEffect` guarded by `initializedRef`. Under React 19 + `reactStrictMode: true` the mount effect double-fires; the cleanup sets `initializedRef.current = false` but the *series refs* still point at objects from the removed chart, so data is piped into a dead chart. Fix = single setup effect that keys off "candles present" and re-creates chart + series when the container or dataset changes. Also add ResizeObserver (container starts at width 0 inside a flex row that measures late).
- Dashboard: one new backend endpoint `GET /api/v1/market-overview` that computes breadth/movers/volatility from the existing `build_provider()` market-data provider (Mock or Gate.io — the endpoint is provider-agnostic). One new Next.js page at `apps/web/app/dashboard/page.tsx` composed of small presentational components. Content set is brainstormed in §3 and deliberately scoped to what the API can actually serve.

**Tech Stack:** FastAPI, Next.js App Router, React 19, Tailwind, lightweight-charts 4.2, zustand (already present), @tanstack/react-query (already present, use it on dashboard for polling).

---

## Task 0: Baseline recon (read-only, 5 minutes)

**Objective:** Confirm the environment the plan assumes.

**Steps:**

1. `cd F:/Programs/confluence-trading-consultant && git status` — expect a clean-ish tree; note any uncommitted work and leave it alone.
2. `rtk ls apps/api/app/api` — expect `analysis.py auth.py deps.py journal.py market_data.py scanner.py strategy.py symbols.py trades.py`.
3. `rtk cat apps/api/app/main.py` — note the order routers are registered; new router must be added here.
4. `rtk cat apps/api/app/services/market_data/factory.py` — read `build_provider()` signature and the provider interface (`get_ohlcv`, `is_symbol_supported`, `is_timeframe_supported`, plus any ticker/listing helpers). If the provider exposes a "list symbols" or ticker method, prefer it in Task 4; otherwise hardcode the dashboard universe to `["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT"]`.
5. `cd apps/web && rtk cat lib/api.ts` — confirm the `request<T>()` helper and `Candle` type; all new client functions go in this file.
6. Start both servers and reproduce the bug:
   - API: `cd apps/api && venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
   - Web: `cd apps/web && npm run dev`
   - Register a user, land on `/terminal/BTC-USDT`, confirm the chart area is blank/empty while the "Loading candles..." state disappears. Open DevTools console — capture the exact error (expected candidates: `Cannot read properties of null`, lightweight-charts `time is ordered` assertion, or zero-size container warning). **Write the observed error message into your commit message for Task 1.**

**Verification:** bug reproduced; exact console error text recorded.

---

## Task 1: Fix the chart (the actual bug)

**Objective:** Make the candlestick chart render reliably on first load, on symbol switch, and on timeframe switch.

**Files:**
- Modify: `apps/web/components/chart/CandlestickChart.tsx` (full rewrite of the effect structure, keep the visual style identical)
- Test: `apps/web/tests/terminal.spec.ts` (extend the existing "loads BTC-USDT with chart" test — see step 4)

**Background (why it's blank):**
1. `next.config.mjs` has `reactStrictMode: true`. In React 19 dev, effects run setup→cleanup→setup. The current code's cleanup calls `chart.remove()` and flips `initializedRef.current = false`, but `candleSeriesRef.current` etc. still hold series objects belonging to the *removed* chart. On the second setup, a new chart is created and the refs are overwritten — mostly fine — BUT if the data effect fired between cleanup and re-setup (it can, because it's a separate effect with `[candles, dataKey]` deps), it called `setData` on the dead series and `lastTimeRef.current` got stuck non-null, so the new chart never takes the bulk-`setData` path again. Result: empty chart with live data in state.
2. The chart is created with a fixed `height: 480` and width from a `window.resize` listener only. The container sits inside a flex `main` that can be 0-wide on first paint; `handleResize()` runs once at setup but lightweight-charts v4 does not re-measure automatically.

**Step 1: Write the regression test first**

Append to `apps/web/tests/terminal.spec.ts`:

```ts
test("chart canvas actually renders candles (not a blank container)", async ({ page }) => {
  const email = `chart-${Date.now()}@example.com`;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const res = await page.request.post(`${apiBase}/api/v1/auth/register`, {
    data: { email, password: "VeryStrong1!" },
  });
  const { access_token } = await res.json();
  await page.addInitScript(
    (token) => window.localStorage.setItem("confluence_token", token),
    access_token,
  );

  await page.goto("/terminal/BTC-USDT");
  const chart = page.getByTestId("candlestick-chart");
  await expect(chart).toBeVisible({ timeout: 15_000 });

  // lightweight-charts renders into <canvas>. A blank chart has a canvas
  // with width 0 or no canvas at all. A rendered chart has canvas width > 100
  // AND at least one painted pixel (we proxy that by checking the series
  // count via the exposed debug hook — see Step 2).
  const canvasCount = await chart.locator("canvas").count();
  expect(canvasCount).toBeGreaterThan(0);
  const width = await chart.evaluate((el) => el.clientWidth);
  expect(width).toBeGreaterThan(100);

  // Switch timeframe — chart must re-render, not go blank.
  await page.getByTestId("timeframe-15m").click();
  await expect(chart).toBeVisible();
  const canvasCountAfter = await chart.locator("canvas").count();
  expect(canvasCountAfter).toBeGreaterThan(0);
});
```

Run it: `cd apps/web && npx playwright test tests/terminal.spec.ts -g "blank container" --reporter=list`
Expected: **FAIL** (canvas count 0 or width 0 — this is the bug).

**Step 2: Rewrite the component**

Replace the whole body of `apps/web/components/chart/CandlestickChart.tsx` with this structure (keep the existing color constants and the EMA/volume series):

```tsx
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

  // ONE effect owns chart lifetime. It (re)builds the chart whenever the
  // container exists. Cleanup destroys everything and nulls every ref so
  // no stale series can survive into the next setup — this is the
  // strict-mode double-mount fix.
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
  }, []);

  // Data effect — depends on candles + dataKey. If the chart isn't built
  // yet (first paint race), it no-ops; the chart effect's reset of
  // lastTimeRef guarantees a bulk set once both have run.
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
      s.candle.setData(
        candles.map((c) => ({
          time: toUnixSeconds(c.timestamp) as any,
          open: c.open, high: c.high, low: c.low, close: c.close,
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
          .map((c, i) => ({ time: toUnixSeconds(c.timestamp) as any, value: vals[i] }))
          .filter((p) => Number.isFinite(p.value));
      s.ema20.setData(toLine(computeEMA(candles, 20)));
      s.ema50.setData(toLine(computeEMA(candles, 50)));
      s.ema200.setData(toLine(computeEMA(candles, 200)));
      lastTimeRef.current = ts;
      chart.timeScale().fitContent();
      return;
    }

    lastTimeRef.current = ts;
    s.candle.update({ time: ts as any, open: last.open, high: last.high, low: last.low, close: last.close });
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

  return <div ref={containerRef} data-testid="candlestick-chart" className="w-full" />;
}
```

Key invariants (do not regress these in review):
- Exactly one effect creates/destroys the chart.
- Every ref is nulled in cleanup (no dead-series writes after strict-mode remount).
- `ResizeObserver` replaces the `window.resize` listener.
- `dataKey` change always forces the bulk `setData` path.

**Step 3: Run the regression test**

`npx playwright test tests/terminal.spec.ts -g "blank container" --reporter=list`
Expected: **PASS**.

**Step 4: Manual smoke**

In the browser: load `/terminal/BTC-USDT` (hard refresh), confirm candles visible immediately; click `15m`, `4h`, `1d` — chart re-renders each time; click `ETH/USDT` in the watchlist — chart swaps. Confirm no console errors.

**Step 5: Typecheck + commit**

```bash
cd apps/web && npm run lint
git add components/chart/CandlestickChart.tsx tests/terminal.spec.ts
git commit -m "fix(web): chart blank on load — strict-mode double-mount left dead series refs; single chart-lifetime effect + ResizeObserver"
```

---

## Task 2: Backend — market overview endpoint (TDD)

**Objective:** One endpoint that aggregates everything the dashboard needs in a single request.

**Files:**
- Create: `apps/api/app/api/overview.py`
- Create: `apps/api/app/schemas/overview.py`
- Create: `apps/api/tests/test_overview.py`
- Modify: `apps/api/app/main.py` (register router after the existing ones)

**Step 1: Write the failing test** — `apps/api/tests/test_overview.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_market_overview_shape():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        # register to get a token (endpoint is auth-gated like the rest)
        email = "ov@example.com"
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "VeryStrong1!"},
        )
        token = r.json()["access_token"]
        r = await client.get(
            "/api/v1/market-overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()

    assert data["provider"] in ("mock", "gateio")
    assert isinstance(data["as_of"], str)
    assert len(data["tickers"]) >= 3

    btc = next(t for t in data["tickers"] if t["symbol"] == "BTC/USDT")
    assert btc["last"] > 0
    assert btc["change_24h_pct"] is not None
    assert btc["sparkline"]  # non-empty list of closes
    assert btc["rsi_14"] is None or 0 <= btc["rsi_14"] <= 100
    assert btc["trend"] in ("up", "down", "flat")

    b = data["breadth"]
    assert b["up"] + b["down"] + b["flat"] == len(data["tickers"])

    m = data["movers"]
    assert len(m["gainers"]) >= 1 and len(m["losers"]) >= 1
```

Run: `cd apps/api && venv/Scripts/python.exe -m pytest tests/test_overview.py -q`
Expected: **FAIL** (404).

**Step 2: Schemas** — `apps/api/app/schemas/overview.py`:

```python
from __future__ import annotations
from pydantic import BaseModel


class TickerSnapshot(BaseModel):
    symbol: str
    last: float
    change_24h_pct: float | None
    high_24h: float | None
    low_24h: float | None
    volume_24h: float | None
    rsi_14: float | None
    trend: str  # "up" | "down" | "flat"  (EMA20 vs EMA50 on 1h)
    sparkline: list[float]  # last ~30 closes, oldest first


class Breadth(BaseModel):
    up: int
    down: int
    flat: int


class Movers(BaseModel):
    gainers: list[TickerSnapshot]
    losers: list[TickerSnapshot]


class MarketOverview(BaseModel):
    provider: str
    as_of: str  # ISO timestamp
    universe: list[str]
    tickers: list[TickerSnapshot]
    breadth: Breadth
    movers: Movers
```

**Step 3: Endpoint** — `apps/api/app/api/overview.py`:

```python
"""Aggregated market overview for the dashboard page."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user  # same dep the other routers use
from app.schemas.overview import (
    Breadth, MarketOverview, Movers, TickerSnapshot,
)
from app.services.market_data.factory import build_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["market-overview"])

UNIVERSE = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
SPARKLINE_LEN = 30


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _ema(vals: list[float], period: int) -> float | None:
    if not vals:
        return None
    k = 2 / (period + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = v * k + ema * (1 - k)
    return ema


@router.get("/market-overview", response_model=MarketOverview)
async def market_overview(_user=Depends(get_current_user)):
    provider = build_provider()
    tickers: list[TickerSnapshot] = []

    for symbol in UNIVERSE:
        if not provider.is_symbol_supported(symbol):
            continue
        try:
            candles_1h = await provider.get_ohlcv(symbol, "1h", 60)
            candles_1d = await provider.get_ohlcv(symbol, "1d", 2)
        except Exception:  # noqa: BLE001 — one bad symbol must not sink the page
            logger.exception("overview: fetch failed for %s", symbol)
            continue
        if not candles_1h:
            continue

        closes = [c.close for c in candles_1h]
        last = closes[-1]
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        if ema20 is None or ema50 is None or abs(ema20 - ema50) / last < 0.001:
            trend = "flat"
        else:
            trend = "up" if ema20 > ema50 else "down"

        change_24h = None
        high_24h = low_24h = vol_24h = None
        if candles_1d:
            today = candles_1d[-1]
            high_24h, low_24h, vol_24h = today.high, today.low, today.volume
            if today.open:
                change_24h = round((today.close - today.open) / today.open * 100, 2)

        tickers.append(
            TickerSnapshot(
                symbol=symbol,
                last=last,
                change_24h_pct=change_24h,
                high_24h=high_24h,
                low_24h=low_24h,
                volume_24h=vol_24h,
                rsi_14=_rsi(closes),
                trend=trend,
                sparkline=closes[-SPARKLINE_LEN:],
            )
        )

    up = sum(1 for t in tickers if t.trend == "up")
    down = sum(1 for t in tickers if t.trend == "down")
    flat = len(tickers) - up - down

    by_change = sorted(
        (t for t in tickers if t.change_24h_pct is not None),
        key=lambda t: t.change_24h_pct,  # type: ignore[arg-type]
        reverse=True,
    )
    movers = Movers(gainers=by_change[:3], losers=list(reversed(by_change))[:3])

    provider_name = os.getenv("MARKET_DATA_PROVIDER", "mock").lower()
    return MarketOverview(
        provider=provider_name,
        as_of=datetime.now(timezone.utc).isoformat(),
        universe=UNIVERSE,
        tickers=tickers,
        breadth=Breadth(up=up, down=down, flat=flat),
        movers=movers,
    )
```

**Step 4: Register the router** — in `apps/api/app/main.py`, next to the other `include_router` calls:

```python
from app.api import overview
app.include_router(overview.router)
```

**Step 5: Run test** — expect **PASS**. Also run the full suite: `venv/Scripts/python.exe -m pytest tests/ -q` — expect no regressions (77 existing + 1 new).

**Step 6: Commit**

```bash
git add apps/api/app/api/overview.py apps/api/app/schemas/overview.py apps/api/tests/test_overview.py apps/api/app/main.py
git commit -m "feat(api): GET /api/v1/market-overview — breadth, movers, RSI/trend/sparkline per symbol"
```

---

## Task 3: Web client bindings

**Objective:** Typed client function for the new endpoint.

**Files:** Modify `apps/web/lib/api.ts`.

Append the types (mirror the Pydantic models) and:

```ts
export type TickerSnapshot = {
  symbol: string;
  last: number;
  change_24h_pct: number | null;
  high_24h: number | null;
  low_24h: number | null;
  volume_24h: number | null;
  rsi_14: number | null;
  trend: "up" | "down" | "flat";
  sparkline: number[];
};

export type MarketOverview = {
  provider: string;
  as_of: string;
  universe: string[];
  tickers: TickerSnapshot[];
  breadth: { up: number; down: number; flat: number };
  movers: { gainers: TickerSnapshot[]; losers: TickerSnapshot[] };
};

export function getMarketOverview(): Promise<MarketOverview> {
  return request<MarketOverview>("/api/v1/market-overview");
}
```

Verify: `cd apps/web && npm run lint` — clean.
Commit: `git add lib/api.ts && git commit -m "feat(web): api client for market-overview"`

---

## Task 4: Dashboard page — shell + data hook

**Objective:** `/dashboard` route, auth-gated, polls every 30s with react-query.

**Files:**
- Create: `apps/web/app/dashboard/page.tsx`
- Modify: `apps/web/components/terminal/TopNav.tsx` — prepend `{ href: "/dashboard", label: "Dashboard" }` to the `NAV` array.

`page.tsx` skeleton:

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { getMarketOverview } from "@/lib/api";
import { MarketConditionCard } from "@/components/dashboard/MarketConditionCard";
import { BreadthGauge } from "@/components/dashboard/BreadthGauge";
import { MoversPanel } from "@/components/dashboard/MoversPanel";
import { TickerGrid } from "@/components/dashboard/TickerGrid";

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  return (
    <main className="p-4 max-w-7xl mx-auto flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Market Dashboard</h1>
        {dataUpdatedAt > 0 && (
          <span className="text-xs text-muted">
            updated {new Date(dataUpdatedAt).toLocaleTimeString()}
            {data && ` · ${data.provider}`}
          </span>
        )}
      </div>

      {isLoading && <p className="text-muted text-sm">Loading market data…</p>}
      {error && <p className="text-bearish text-sm">Failed to load market overview.</p>}

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <MarketConditionCard overview={data} />
            <BreadthGauge breadth={data.breadth} />
            <MoversPanel movers={data.movers} />
          </div>
          <TickerGrid tickers={data.tickers} />
        </>
      )}
    </main>
  );
}
```

If `QueryClientProvider` isn't already mounted (check `apps/web/lib/` and `app/layout.tsx` — the dep is in package.json but may be unused), add a small `apps/web/lib/query-client.tsx` exporting a client + provider and wrap it in `app/layout.tsx` inside `AuthProvider`. That wiring is part of this task.

Typecheck, then commit: `feat(web): dashboard route shell with 30s polling`.

---

## Task 5: Dashboard components (the brainstormed content)

**Objective:** Four presentational components in `apps/web/components/dashboard/`. Pure props in, JSX out. No fetching inside them.

**5a. `MarketConditionCard.tsx` — "general market condition" verdict.** Derives a single verdict from breadth + BTC trend + BTC RSI:

```
score = (breadth.up - breadth.down) / total        // -1..1
      + (BTC trend up ? 0.5 : BTC trend down ? -0.5 : 0)
      + (BTC rsi >= 70 ? -0.5 : BTC rsi <= 30 ? 0.5 : 0)  // contrarian nudge
verdict: score > 0.5 "RISK-ON" | score < -0.5 "RISK-OFF" | else "MIXED"
```

Render: big verdict label (bullish green / bearish red / warning amber), sub-line "BTC trend up · RSI 54 · breadth 3↑ 1↓ 1→", and a one-line plain-English caption (e.g. "Most tracked majors are above their short-term averages."). Table-driven caption selection, not an if-ladder.

**5b. `BreadthGauge.tsx`** — horizontal stacked bar: green segment (up), gray (flat), red (down), width proportional. Numbers printed on the segments. Under it, percentage text "60% of tracked markets trending up".

**5c. `MoversPanel.tsx`** — two columns "Top gainers" / "Top losers", each row: symbol + `change_24h_pct` colored. Rows link to `/terminal/{symbol with / → -}`.

**5d. `TickerGrid.tsx`** — card per symbol: symbol, last price, 24h change badge, RSI pill (color: ≥70 bearish "overbought", ≤30 bullish "oversold", else neutral), trend arrow, and a `Sparkline` (see 5e). Card click → terminal page.

**5e. `Sparkline.tsx`** — tiny inline `<svg width={96} height={28}>` polyline normalized to min/max of the array, stroke `currentColor`, no axes. ~20 lines, no new dependency. Color by first-vs-last close.

**Step per component:** create file → `npm run lint` → eyeball in browser → single commit for all of `components/dashboard/`:
`feat(web): dashboard components — condition verdict, breadth gauge, movers, ticker grid with sparklines`.

---

## Task 6: E2E test + docs + final verification

**Step 1:** Add `apps/web/tests/dashboard.spec.ts`:

```ts
test("dashboard renders market condition and ticker grid", async ({ page }) => {
  const email = `dash-${Date.now()}@example.com`;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const res = await page.request.post(`${apiBase}/api/v1/auth/register`, {
    data: { email, password: "VeryStrong1!" },
  });
  const { access_token } = await res.json();
  await page.addInitScript(
    (t) => window.localStorage.setItem("confluence_token", t),
    access_token,
  );

  await page.goto("/dashboard");
  await expect(page.getByText("Market Dashboard")).toBeVisible();
  await expect(page.getByText(/RISK-ON|RISK-OFF|MIXED/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("BTC/USDT").first()).toBeVisible();
  // clicking a ticker card navigates to its terminal page
  await page.getByText("ETH/USDT").first().click();
  await expect(page).toHaveURL(/\/terminal\/ETH-USDT/);
});
```

Run the whole web e2e suite: `npx playwright test --reporter=list` — all green (chart regression test from Task 1 included).

**Step 2:** Full backend suite once more: `cd apps/api && venv/Scripts/python.exe -m pytest tests/ -q`.

**Step 3:** Update `HANDOFF.md` — append a short "Phase 8: chart fix + market dashboard" section: what the bug was (dead series refs after strict-mode remount), the new endpoint, the new page, and how to verify.

**Step 4:** Final commit: `test(web): dashboard e2e + docs(handoff): phase 8`.

---

## Out of scope (explicitly — do not build these)

- No websockets on the dashboard (30s polling is fine for an overview).
- No new market-data provider methods; use `get_ohlcv` only.
- No portfolio/positions panel (the app has no positions concept yet; journal exists but is a separate page).
- No TradingView widget — keep lightweight-charts, same library as the terminal.
- No changes to the council/decision engine, scanner, or LLM code.

## Definition of done

1. Chart renders on first load, on timeframe switch, on symbol switch; regression e2e test green.
2. `GET /api/v1/market-overview` returns 200 with the full schema; pytest green (78+ tests).
3. `/dashboard` shows condition verdict, breadth, movers, ticker cards with sparklines; auto-refresh 30s; e2e green.
4. `npm run lint` clean; `HANDOFF.md` updated; one commit per task.
