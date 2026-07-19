# Phase 9: Full TradingView Chart + Multi-Venue Dashboard + Auto-Analysis

> **For the implementing model:** You are working on `F:\Programs\confluence-trading-consultant`.
> Read this file top to bottom before touching code. Every task lists exact files and exact verification commands.
> Repo layout: `apps/api` (FastAPI, Python 3.14, venv at `apps/api/venv`), `apps/web` (Next.js 16 + React 19 + Tailwind).
> API runs on `http://localhost:8000`, web on `http://localhost:3000`.
> Web `npm run lint` = `tsc --noEmit`. API tests = `apps/api/venv/Scripts/python.exe -m pytest tests/ -q` from `apps/api/`.
> Commit after every task. TDD where it makes sense (API endpoints), manual verification for visual components.

**Goal:** Replace the lightweight-charts candlestick chart with a full TradingView Advanced Chart widget (free, embeddable) that supports any symbol from any configured venue (CEX or DEX). Redesign the main dashboard as a trading terminal with the chart as the centerpiece, symbol search across venues, auto-analysis on chart open, and complete statistics panel.

**Architecture:**
- **Chart layer:** TradingView Advanced Chart widget (script-tag embed, not lightweight-charts) for the main terminal page. Keep lightweight-charts for dashboard sparklines only.
- **Venue layer:** Abstract `MarketDataProvider` to support multiple backends. Add `venue` field to symbol metadata. New endpoints for venue discovery and symbol search.
- **Dashboard layer:** Responsive terminal layout — chart hero (60-70% width), side panels for analysis + order book, bottom strip for scanner + positions.
- **Auto-analysis:** Optional toggle; when a chart is opened or symbol changed, trigger a council analysis run in the background and stream results to the side panel.
- **Complete stats:** Expand the existing `DecisionConsole` and `TradePanel` to show all gate scores, model opinions, risk flags, and trade plan in a tabbed side panel.

**Tech Stack:** FastAPI, Next.js App Router, React 19, Tailwind, TradingView widget (CDN), @tanstack/react-query, zustand.

---

## Task 0: Baseline recon (read-only, 5 minutes)

**Objective:** Confirm current state before making changes.

**Steps:**
1. `cd F:/Programs/confluence-trading-consultant && git status` — note any uncommitted work.
2. Verify both servers are running (API :8000, web :3000). If not, start them:
   - API: `cd apps/api && venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
   - Web: `cd apps/web && npm run dev`
3. Open `http://localhost:3000/dashboard` in browser — confirm the dashboard renders with the Phase 8 components (MarketConditionCard, BreadthGauge, MoversPanel, TickerGrid).
4. Open `http://localhost:3000/terminal/BTC-USDT` — confirm the lightweight-charts candlestick chart renders (it should after Phase 8 fix).
5. Read `apps/api/app/services/market_data/base.py` — confirm the `MarketDataProvider` Protocol interface.
6. Read `apps/api/app/services/market_data/gateio_rest.py` — note the `DEFAULT_UNIVERSE`, `GATEIO_INTERVALS`, and `list_spot_pairs()` method.
7. Read `apps/api/app/api/symbols.py` — note the `SymbolOut` schema and the `sync_symbols` endpoint.
8. Read `apps/web/components/decision/DecisionConsole.tsx` and `TradePanel.tsx` — note their current props and rendering.

**Verification:** Both pages load, chart renders, dashboard shows data. Record any console errors.

---

## Task 1: Multi-venue provider abstraction (backend)

**Objective:** Make the market data provider support multiple venues, not just Gate.io.

**Background:** Currently `build_provider()` returns a single provider based on `MARKET_DATA_PROVIDER` env var. The `SymbolMeta` table has `exchange` field but it's just a string label. We need:
- A registry of providers (Gate.io, Binance, Mock, etc.)
- Each provider exposes its `name`, `supported_symbols()`, and `is_symbol_supported()`
- A new endpoint to list all configured venues
- A new endpoint to search symbols across all venues

**Files:**
- Modify: `apps/api/app/services/market_data/factory.py`
- Modify: `apps/api/app/services/market_data/base.py`
- Create: `apps/api/app/services/market_data/binance_rest.py` (minimal — just enough for symbol listing and OHLCV)
- Create: `apps/api/app/services/market_data/registry.py`
- Modify: `apps/api/app/api/symbols.py`
- Create: `apps/api/tests/test_venues.py`

**Step 1: Extend the Protocol** — in `base.py`, add to `MarketDataProvider`:
```python
@property
def venue_id(self) -> str: ...  # "gateio", "binance", "mock"

@property
def venue_label(self) -> str: ...  # "Gate.io", "Binance", "Mock"

def supported_symbols(self) -> list[str]: ...
```

**Step 2: Registry** — `registry.py`:
```python
from __future__ import annotations
from app.services.market_data.gateio_rest import GateioRestProvider
from app.services.market_data.mock_provider import MockMarketDataProvider

_VENUE_REGISTRY: dict[str, type[MarketDataProvider]] = {
    "mock": MockMarketDataProvider,
    "gateio": GateioRestProvider,
    # "binance": BinanceRestProvider,  # Task 1b
}

def list_venues() -> list[dict[str, str]]:
    return [
        {"id": k, "label": k, "enabled": True}
        for k in _VENUE_REGISTRY
    ]

def get_provider(venue_id: str) -> MarketDataProvider:
    if venue_id not in _VENUE_REGISTRY:
        raise ValueError(f"Unknown venue: {venue_id}")
    return _VENUE_REGISTRY[venue_id]()

def all_providers() -> list[MarketDataProvider]:
    return [cls() for cls in _VENUE_REGISTRY.values()]
```

**Step 3: Update factory.py** — `build_provider()` stays for backward compat (reads env var), add `build_provider_for_venue(venue_id: str)`.

**Step 4: Update GateioRestProvider** — add `venue_id = "gateio"`, `venue_label = "Gate.io"`. Add `list_spot_pairs()` if not present (it exists in `symbols.py` via `provider.list_spot_pairs()` — verify and move to provider).

**Step 5: New endpoints in symbols.py** — append:
```python
@router.get("/venues", response_model=list[dict[str, str]])
def list_venues_endpoint(_user=Depends(get_current_user)):
    from app.services.market_data.registry import list_venues
    return list_venues()

@router.get("/search", response_model=list[SymbolOut])
async def search_symbols(
    q: str = Query(..., min_length=1),
    _user=Depends(get_current_user),
):
    """Search across all configured venues for symbols matching query."""
    from app.services.market_data.registry import all_providers
    results = []
    seen = set()
    for provider in all_providers():
        for sym in provider.supported_symbols():
            if q.upper() in sym.upper() and sym not in seen:
                seen.add(sym)
                results.append(SymbolOut(
                    symbol=sym, exchange=provider.venue_id,
                    base=sym.split("/")[0], quote=sym.split("/")[1],
                    is_active=True, tick_size=None, min_qty=None,
                ))
    return results[:50]  # cap results
```

**Step 6: Test** — `tests/test_venues.py`:
```python
@pytest.mark.asyncio
async def test_list_venues():
    ...  # assert /api/v1/symbols/venues returns >= 2 venues

@pytest.mark.asyncio
async def test_search_symbols():
    ...  # assert /api/v1/symbols/search?q=BTC returns BTC/USDT
```

Run: `venv/Scripts/python.exe -m pytest tests/test_venues.py -q` → expect PASS.

**Step 7: Commit** — `git add ... && git commit -m "feat(api): multi-venue provider registry + search endpoint"`

---

## Task 2: TradingView Advanced Chart widget integration (frontend)

**Objective:** Replace the lightweight-charts component on `/terminal/[symbol]` with TradingView's free embeddable Advanced Chart widget.

**Background:** TradingView provides a free widget via CDN: `https://s3.tradingview.com/tv.js`. The widget is loaded via a script tag and initialized with `new TradingView.widget({...})`. It supports any symbol that TradingView has data for (thousands of CEX + DEX pairs). The widget handles its own data feed — we don't need to fetch candles.

**Key config:**
- `symbol`: TradingView format, e.g. `GATEIO:BTCUSDT` for Gate.io, `BINANCE:BTCUSDT` for Binance
- `interval`: `1`, `5`, `15`, `60`, `240`, `D`
- `theme`: `dark`
- `style`: `1` (candles)
- `locale`: `en`
- `toolbar_bg`: `#0B0F14`
- `enable_publishing`: `false`
- `hide_top_toolbar`: `false`
- `allow_symbol_change`: `true` (user can change symbol inside the widget)
- `container_id`: DOM element ID

**Files:**
- Create: `apps/web/components/chart/TradingViewChart.tsx`
- Modify: `apps/web/app/terminal/[symbol]/page.tsx` — replace `CandlestickChart` with `TradingViewChart`
- Modify: `apps/web/components/terminal/TimeframeSelector.tsx` — map our timeframes to TV intervals

**Step 1: Create the component** — `TradingViewChart.tsx`:

```tsx
"use client";

import { useEffect, useRef } from "react";

type Props = {
  symbol: string;        // e.g. "BTC/USDT"
  venue: string;         // e.g. "gateio", "binance"
  interval: string;      // e.g. "1h", "15m"
  onSymbolChange?: (symbol: string, venue: string) => void;
};

const VENUE_TO_TV_PREFIX: Record<string, string> = {
  gateio: "GATEIO",
  binance: "BINANCE",
  mock: "GATEIO",  // fallback
};

const TF_TO_TV_INTERVAL: Record<string, string> = {
  "1m": "1",
  "5m": "5",
  "15m": "15",
  "1h": "60",
  "4h": "240",
  "1d": "D",
};

export function TradingViewChart({ symbol, venue, interval, onSymbolChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;

    // Load TradingView script if not already loaded
    const scriptId = "tradingview-widget-script";
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement("script");
      script.id = scriptId;
      script.src = "https://s3.tradingview.com/tv.js";
      script.async = true;
      document.body.appendChild(script);
    }

    const initWidget = () => {
      if (!(window as any).TradingView) return;
      if (widgetRef.current) {
        widgetRef.current.remove();
        widgetRef.current = null;
      }

      const prefix = VENUE_TO_TV_PREFIX[venue] || "GATEIO";
      const tvSymbol = `${prefix}:${symbol.replace("/", "")}`;
      const tvInterval = TF_TO_TV_INTERVAL[interval] || "60";

      widgetRef.current = new (window as any).TradingView.widget({
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
        container_id: el.id,
        studies: ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"],
        show_popup_button: true,
        popup_width: "1000",
        popup_height: "650",
        // Callback when user changes symbol inside the widget
        ...(onSymbolChange && {
          onSymbolChange: (newSymbol: string) => {
            // newSymbol comes as "GATEIO:BTCUSDT" — parse it
            const [newVenue, newPair] = newSymbol.split(":");
            const formatted = newPair.replace(/([A-Z]+)(USDT)$/, "$1/$2");
            onSymbolChange(formatted, newVenue.toLowerCase());
          },
        }),
      });
    };

    if ((window as any).TradingView) {
      initWidget();
    } else {
      script!.onload = initWidget;
    }

    return () => {
      if (widgetRef.current) {
        widgetRef.current.remove();
        widgetRef.current = null;
      }
    };
  }, [symbol, venue, interval, onSymbolChange]);

  return (
    <div
      id={`tv-chart-${symbol.replace("/", "-")}`}
      ref={containerRef}
      className="w-full h-[480px] md:h-[560px] lg:h-[640px]"
    />
  );
}
```

**Step 2: Update terminal page** — in `app/terminal/[symbol]/page.tsx`:
- Replace `import { CandlestickChart }` with `import { TradingViewChart }`
- Remove the `candles`, `freshness`, `latestTs` state and the candle-fetching `useEffect` (TV widget loads its own data)
- Keep the `timeframe` state and `TimeframeSelector`
- Add `venue` state (default "gateio")
- Replace the chart JSX:
```tsx
<TradingViewChart
  symbol={displaySymbol}
  venue={venue}
  interval={timeframe}
  onSymbolChange={(newSym, newVenue) => {
    router.push(`/terminal/${newSym.replace("/", "-")}?venue=${newVenue}`);
  }}
/>
```
- Keep the `Run Analysis` button and `DecisionConsole` / `TradePanel` side panel

**Step 3: Handle venue in URL** — read `?venue=` from search params, default to "gateio".

**Step 4: Typecheck** — `npm run lint` → clean.

**Step 5: Manual verification** — load `/terminal/BTC-USDT`, confirm:
- TradingView widget loads with dark theme
- Candles render (real data from TV, not mock)
- Timeframe buttons (1m, 5m, 15m, 1h, 4h, 1d) switch the chart interval
- Changing symbol in the widget's symbol search updates the URL

**Step 6: Commit** — `git add ... && git commit -m "feat(web): TradingView Advanced Chart widget replaces lightweight-charts on terminal"`

---

## Task 3: Symbol search + venue selector (frontend)

**Objective:** Add a symbol search bar and venue dropdown to the terminal page so users can open any pair from any configured venue.

**Files:**
- Create: `apps/web/components/terminal/SymbolSearch.tsx`
- Create: `apps/web/components/terminal/VenueSelector.tsx`
- Modify: `apps/web/app/terminal/[symbol]/page.tsx` — integrate search + venue selector
- Modify: `apps/web/lib/api.ts` — add `searchSymbols()` and `listVenues()`

**Step 1: API bindings** — append to `lib/api.ts`:
```ts
export type Venue = { id: string; label: string; enabled: boolean };
export type SymbolSearchResult = {
  symbol: string;
  exchange: string;
  base: string;
  quote: string;
  is_active: boolean;
};

export function listVenues(): Promise<Venue[]> {
  return request<Venue[]>("/api/v1/symbols/venues");
}

export function searchSymbols(q: string): Promise<SymbolSearchResult[]> {
  return request<SymbolSearchResult[]>(`/api/v1/symbols/search?q=${encodeURIComponent(q)}`);
}
```

**Step 2: SymbolSearch component** — debounced input, dropdown results, keyboard navigation:
```tsx
"use client";
import { useState, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchSymbols } from "@/lib/api";
import { useRouter } from "next/navigation";

export function SymbolSearch({ currentVenue }: { currentVenue: string }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["symbol-search", q],
    queryFn: () => searchSymbols(q),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });

  const onSelect = (symbol: string, venue: string) => {
    router.push(`/terminal/${symbol.replace("/", "-")}?venue=${venue}`);
    setOpen(false);
    setQ("");
  };

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search symbol..."
        className="bg-panel border border-border rounded px-2 py-1 text-sm w-48 focus:border-info outline-none"
      />
      {open && q.length >= 2 && (
        <div className="absolute top-full mt-1 left-0 w-64 bg-panel border border-border rounded shadow-lg z-50 max-h-60 overflow-auto">
          {isLoading && <p className="text-xs text-muted p-2">Searching…</p>}
          {data?.map((s) => (
            <button
              key={`${s.exchange}:${s.symbol}`}
              onClick={() => onSelect(s.symbol, s.exchange)}
              className="w-full text-left px-3 py-1.5 text-sm hover:bg-border/40 flex justify-between"
            >
              <span className="text-primary">{s.symbol}</span>
              <span className="text-muted text-xs">{s.exchange}</span>
            </button>
          ))}
          {data?.length === 0 && <p className="text-xs text-muted p-2">No results</p>}
        </div>
      )}
    </div>
  );
}
```

**Step 3: VenueSelector** — simple dropdown:
```tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { listVenues } from "@/lib/api";

export function VenueSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data } = useQuery({ queryKey: ["venues"], queryFn: listVenues, staleTime: Infinity });
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-panel border border-border rounded px-2 py-1 text-sm outline-none focus:border-info"
    >
      {data?.map((v) => (
        <option key={v.id} value={v.id}>{v.label}</option>
      ))}
    </select>
  );
}
```

**Step 4: Integrate into terminal page** — add both to the header bar, left of the timeframe selector.

**Step 5: Typecheck + manual test** — search "BTC", click result, chart switches. Change venue, chart reloads with new prefix.

**Step 6: Commit** — `feat(web): symbol search + venue selector on terminal`

---

## Task 4: Auto-analysis on chart open / symbol change

**Objective:** When the user opens a chart or changes symbol/timeframe, optionally auto-run the council analysis and stream results to the side panel.

**Background:** The `runAnalysis()` API already exists. We just need to:
1. Add a toggle (zustand store or local state) for "Auto-analyze on change"
2. When symbol/timeframe changes and toggle is on, call `runAnalysis()` automatically
3. Show a loading state in the side panel while analysis runs

**Files:**
- Create: `apps/web/lib/analysis-store.ts` (zustand store for auto-analysis toggle + current run)
- Modify: `apps/web/app/terminal/[symbol]/page.tsx` — add auto-analysis effect
- Modify: `apps/web/components/decision/DecisionConsole.tsx` — add loading skeleton

**Step 1: Zustand store** — `lib/analysis-store.ts`:
```ts
import { create } from "zustand";
import type { RunOut } from "@/lib/api";

interface AnalysisStore {
  autoAnalyze: boolean;
  setAutoAnalyze: (v: boolean) => void;
  currentRun: RunOut | null;
  setCurrentRun: (run: RunOut | null) => void;
  isAnalyzing: boolean;
  setIsAnalyzing: (v: boolean) => void;
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  autoAnalyze: false,  // default off — user opts in
  setAutoAnalyze: (v) => set({ autoAnalyze: v }),
  currentRun: null,
  setCurrentRun: (run) => set({ currentRun: run }),
  isAnalyzing: false,
  setIsAnalyzing: (v) => set({ isAnalyzing: v }),
}));
```

**Step 2: Auto-analysis effect** — in terminal page, add:
```tsx
const { autoAnalyze, setCurrentRun, setIsAnalyzing } = useAnalysisStore();

useEffect(() => {
  if (!autoAnalyze || !user) return;
  setIsAnalyzing(true);
  runAnalysis({ symbol: displaySymbol, timeframe, strategy: "balanced" })
    .then((result) => setCurrentRun(result))
    .catch(() => setCurrentRun(null))
    .finally(() => setIsAnalyzing(false));
}, [displaySymbol, timeframe, autoAnalyze, user]);
```

**Step 3: Toggle UI** — add a small toggle switch in the terminal header:
```tsx
<label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer">
  <input
    type="checkbox"
    checked={autoAnalyze}
    onChange={(e) => setAutoAnalyze(e.target.checked)}
    className="accent-info"
  />
  Auto-analyze
</label>
```

**Step 4: DecisionConsole loading state** — when `isAnalyzing` is true, show a skeleton/pulse instead of empty state.

**Step 5: Commit** — `feat(web): auto-analysis toggle on symbol/timeframe change`

---

## Task 5: Complete statistics panel (side panel redesign)

**Objective:** Redesign the right-side panel to show ALL analysis data comprehensively: gate scores, model opinions, risk flags, trade plan, and historical runs for the current symbol.

**Files:**
- Create: `apps/web/components/decision/GateScores.tsx`
- Create: `apps/web/components/decision/ModelOpinions.tsx`
- Create: `apps/web/components/decision/RiskFlags.tsx`
- Create: `apps/web/components/decision/TradePlanDetail.tsx`
- Create: `apps/web/components/decision/RunHistory.tsx`
- Modify: `apps/web/app/terminal/[symbol]/page.tsx` — compose new panels

**Step 1: GateScores** — horizontal bar chart per gate (name, score 0-1, color by threshold). Use simple div bars, no chart library.

**Step 2: ModelOpinions** — table: role | direction | confidence | reason. Color direction (LONG=green, SHORT=red, WAIT=gray).

**Step 3: RiskFlags** — if any `risk_flags` present, show as red warning badges. If none, show green "No risk flags".

**Step 4: TradePlanDetail** — expand the existing `TradePanel` to show ALL fields: entry, stop, TP, R:R, position size, invalidation, risk review, synthesis. Use a grid layout.

**Step 5: RunHistory** — new API endpoint `GET /api/v1/analysis/history?symbol=BTC/USDT&limit=10`. Add to `analysis.py`:
```python
@router.get("/history")
async def history(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.engine.runner import list_runs
    runs = list_runs(db, symbol=symbol, limit=limit)
    return [run_to_out(r) for r in runs]
```
Add client function in `lib/api.ts`.

Show as a compact list: time, final_state, composite_score, direction. Click to load that run into the panel.

**Step 6: Compose** — terminal page right panel becomes tabbed:
- Tab 1: "Current Analysis" (DecisionConsole + TradePlanDetail)
- Tab 2: "Gates & Models" (GateScores + ModelOpinions + RiskFlags)
- Tab 3: "History" (RunHistory)

Use simple state tabs (no library needed).

**Step 7: Typecheck + commit** — `feat(web): complete statistics panel with tabs — gates, models, risk, history`

---

## Task 6: Main dashboard redesign (terminal layout)

**Objective:** Redesign `/dashboard` as a trading terminal layout with the chart as the centerpiece, not a simple grid.

**Background:** The current dashboard is a 3-column grid of cards. The new design should be:
- Full-width layout, no max-w-7xl constraint
- Top bar: symbol search (big, prominent), venue selector, timeframe selector, auto-analyze toggle
- Main area: chart takes 70% width (left), side panel 30% (right) — same components as terminal page
- Bottom strip: scanner results (latest notable scans), open journal positions, recent trades
- Responsive: on mobile, stack vertically (chart → panel → bottom strip)

**Files:**
- Modify: `apps/web/app/dashboard/page.tsx` — full rewrite
- Create: `apps/web/components/dashboard/ScannerStrip.tsx`
- Create: `apps/web/components/dashboard/JournalStrip.tsx`
- Modify: `apps/web/components/terminal/TopNav.tsx` — maybe simplify on dashboard (hide some nav items when on dashboard?)

**Step 1: Dashboard page rewrite** — compose:
```tsx
<main className="h-screen flex flex-col">
  {/* Top bar */}
  <header className="h-12 border-b border-border bg-panel flex items-center px-4 gap-3">
    <SymbolSearch currentVenue={venue} />
    <VenueSelector value={venue} onChange={setVenue} />
    <TimeframeSelector value={timeframe} onChange={setTimeframe} />
    <label className="ml-auto ...">Auto-analyze toggle</label>
  </header>

  {/* Main content */}
  <div className="flex-1 flex overflow-hidden">
    {/* Chart area */}
    <div className="flex-[7] min-w-0 border-r border-border">
      <TradingViewChart symbol={symbol} venue={venue} interval={timeframe} />
    </div>

    {/* Side panel */}
    <div className="flex-[3] min-w-0 overflow-auto bg-panel">
      <AnalysisTabs run={currentRun} isAnalyzing={isAnalyzing} />
    </div>
  </div>

  {/* Bottom strip */}
  <div className="h-48 border-t border-border bg-panel flex gap-0 overflow-hidden">
    <div className="flex-1 border-r border-border overflow-auto p-2">
      <ScannerStrip />
    </div>
    <div className="flex-1 overflow-auto p-2">
      <JournalStrip />
    </div>
  </div>
</main>
```

**Step 2: ScannerStrip** — poll `GET /api/v1/scanner/latest?limit=10`, show compact table: symbol, final_state, time. Click → open that symbol in chart.

**Step 3: JournalStrip** — poll `GET /api/v1/journal?open_only=true&limit=10`, show open positions: symbol, side, entry, PnL. Click → open symbol.

**Step 4: Typecheck + manual verification** — dashboard loads as terminal layout, chart is large, side panel shows analysis, bottom strips scroll.

**Step 5: Commit** — `feat(web): dashboard redesign as trading terminal — chart hero + side panel + bottom strips`

---

## Task 7: E2E tests + docs + final verification

**Step 1: E2E tests** — `tests/dashboard.spec.ts` and `tests/terminal.spec.ts`:
- Dashboard: chart widget loads (check for TV container), symbol search works, venue switch works
- Terminal: TV chart renders, auto-analysis toggle works, side panel tabs switch

**Step 2: Full test suite** — `pytest tests/ -q` + `npm run lint` + `npx playwright test --reporter=list`

**Step 3: Update HANDOFF.md** — append Phase 9 section documenting:
- TradingView widget integration
- Multi-venue abstraction
- Auto-analysis feature
- Dashboard terminal layout
- New components list

**Step 4: Final commit** — `docs(handoff): phase 9 — TV widget, multi-venue, auto-analysis, terminal dashboard`

---

## Out of scope (explicitly)

- **Real-time WebSocket data** — TradingView widget handles its own data feed. Our backend candle endpoints stay for the scanner and sparklines.
- **DEX on-chain data** — The provider abstraction supports it, but no DEX provider is implemented in this phase. The registry pattern allows adding Uniswap/GMX/etc. later.
- **Order execution** — The existing paper trading endpoints stay unchanged. No live trading.
- **Drawing tools persistence** — TradingView widget has drawing tools but persistence requires TV's paid features or custom implementation. Out of scope.
- **Mobile app** — Responsive web only.

## Definition of done

1. TradingView Advanced Chart widget renders on `/terminal/[symbol]` and `/dashboard` with real market data (not mock sine-wave).
2. Symbol search works across all configured venues (Gate.io, Mock, and any added).
3. Venue selector switches the chart data source.
4. Auto-analysis toggle runs council analysis automatically on symbol/timeframe change.
5. Side panel shows complete statistics: gates, models, risk flags, trade plan, history.
6. Dashboard is a full terminal layout: chart hero + side panel + bottom scanner/journal strips.
7. All tests pass (backend + frontend lint + e2e).
8. HANDOFF.md updated.

## Files summary (new + modified)

**New backend:**
- `apps/api/app/services/market_data/registry.py`
- `apps/api/app/services/market_data/binance_rest.py` (minimal scaffold)
- `apps/api/tests/test_venues.py`

**Modified backend:**
- `apps/api/app/services/market_data/base.py` — add venue_id, venue_label
- `apps/api/app/services/market_data/factory.py` — add build_provider_for_venue
- `apps/api/app/services/market_data/gateio_rest.py` — add venue attrs
- `apps/api/app/api/symbols.py` — add /venues, /search
- `apps/api/app/api/analysis.py` — add /history

**New frontend:**
- `apps/web/components/chart/TradingViewChart.tsx`
- `apps/web/components/terminal/SymbolSearch.tsx`
- `apps/web/components/terminal/VenueSelector.tsx`
- `apps/web/lib/analysis-store.ts`
- `apps/web/components/decision/GateScores.tsx`
- `apps/web/components/decision/ModelOpinions.tsx`
- `apps/web/components/decision/RiskFlags.tsx`
- `apps/web/components/decision/TradePlanDetail.tsx`
- `apps/web/components/decision/RunHistory.tsx`
- `apps/web/components/dashboard/ScannerStrip.tsx`
- `apps/web/components/dashboard/JournalStrip.tsx`

**Modified frontend:**
- `apps/web/app/terminal/[symbol]/page.tsx` — TV widget, search, venue, auto-analysis
- `apps/web/app/dashboard/page.tsx` — terminal layout
- `apps/web/lib/api.ts` — new client functions
- `apps/web/components/decision/DecisionConsole.tsx` — loading state
- `apps/web/components/terminal/TimeframeSelector.tsx` — TV interval mapping
- `apps/web/tests/dashboard.spec.ts`
- `apps/web/tests/terminal.spec.ts`

**Docs:**
- `HANDOFF.md` — Phase 9 section
