# Phase 10+: UI/UX Repair + Full-Symbol Coverage + Real Dashboard

> **Source of truth for the implementing model.** This plan fixes the ugly UI
> surfaces, adds complete CEX/DEX pair listings, and rebuilds the dashboard
> into a real trading terminal overview page. Every other page gets
> populated with real data instead of placeholder text.

---

## Read this first

The project lives at `F:\Programs\confluence-trading-consultant`.
Backend is FastAPI on `:8000`, frontend is Next.js on `:3000`. They are
already wired up and running.

### What's already built (backend, in this session)

**6 venue providers registered**: mock, gateio, **binance, bybit, kraken, okx**.
Each has `get_all_spot_pairs()` and `search_pairs()` — cached 1h, sorted by
24h volume. The full provider list is at `apps/api/app/services/market_data/registry.py`.

**Aggregate endpoint**: `GET /api/v1/market/top?limit=25` returns the top N
pairs by volume across ALL venues, deduplicated by `base_venue`. Also
`GET /api/v1/market/tv-prefixes` returns the TradingView exchange prefix for
each venue (GATEIO, BINANCE, BYBIT, KRAKEN, OKX).

**TV prefix map** (use this in `TradingViewChart.tsx`):

| venue_id | TV prefix | Symbol format |
|----------|-----------|---------------|
| gateio | GATEIO | GATEIO:BTCUSDT |
| binance | BINANCE | BINANCE:BTCUSDT |
| bybit | BYBIT | BYBIT:BTCUSDT |
| kraken | KRAKEN | KRAKEN:XBTUSDT |
| okx | OKX | OKX:BTC-USDT |

**You do NOT need to build these.** They're done. Focus on the frontend
and remaining tasks below.

### Files you must read before starting

- `apps/web/lib/api.ts` — every backend route the frontend can call
- `apps/web/lib/auth-context.tsx` — how to gate pages
- `apps/web/lib/query-client.tsx` — react-query setup
- `apps/web/components/terminal/TopNav.tsx` — site nav
- `apps/web/app/terminal/[symbol]/page.tsx` — the most-polished existing page
- `apps/web/app/dashboard/page.tsx` — the page you're rebuilding
- `apps/api/app/services/market_data/gateio_rest.py` — the only exchange

**Run `npm run lint` after every task.** Zero errors is the bar.

---

## The audit — what's wrong

| # | Problem | Where |
|---|---------|-------|
| 1 | Dashboard is just a TV chart on a blank page with one stat card | `app/dashboard/page.tsx` |
| 2 | `TickerGrid`, `MoversPanel`, `BreadthGauge`, `MarketConditionCard`, `Sparkline` exist but are barely used | `components/dashboard/*` |
| 3 | Only 12 hand-curated pairs in `DEFAULT_UNIVERSE` | `gateio_rest.py:25-37` |
| 4 | No DEX support, no pair browser, no exchange filter | API + UI |
| 5 | `/alerts` shows empty state with no way to create an alert | `app/alerts/page.tsx` |
| 6 | `/analytics` looks like a spreadsheet | `app/analytics/page.tsx` |
| 7 | `/journal` is functional but bare — no charts, no filters | `app/journal/page.tsx` |
| 8 | `/scan` runs but doesn't show per-symbol progress nicely | `app/scan/page.tsx` |
| 9 | `/settings` is form-only — no way to import/export strategies | `app/settings/page.tsx` |
| 10 | Login + register are dev-quality | `app/(auth)/login/page.tsx` |
| 11 | No global keyboard shortcuts (no `/` to search, no Esc) | n/a |
| 12 | `OrderBook` is built but never rendered in the terminal | `components/terminal/OrderBook.tsx` |
| 13 | `GateScores`, `RiskFlags` exist but no summary view at-a-glance | `components/decision/*` |
| 14 | No notification toaster for new alerts / analysis complete | n/a |
| 15 | Dark mode looks flat, no depth/blur/elevation | `app/globals.css` |
| 16 | No favicon, no loading skeletons, no empty-state illustrations | n/a |
| 17 | No backtest page even though backtest engine is built | n/a |
| 18 | No "alerts history" view — only active alerts | n/a |
| 19 | Symbol search has no filters (quote currency, exchange, sort) | `SymbolSearch.tsx` |
| 20 | No "watchlist" feature | n/a |

That's 20 items. Below is the prioritized plan, sized for a cheaper
model to execute task-by-task.

---

## 11 tasks, ordered by impact

Each task: **what**, **where**, **exact code shape**, **verify**. Build
in order — later tasks depend on earlier ones.

---

### Task 1: Complete pair coverage — full Gate.io universe

**Why it matters:** Right now the API hardcodes 12 pairs. The TV widget
can already show any pair, but the backend gates you from searching or
analyzing anything else.

**Backend change** — `apps/api/app/services/market_data/gateio_rest.py`:

1. Add `_spot_pairs_cache: list[dict] | None = None` to the provider.
2. Add async method `async def get_all_spot_pairs(self) -> list[dict]`:
   - Call `/spot/currency_pairs` (already exposed via `list_spot_pairs`)
   - Filter: `trade_status == "tradable"`, `quote == "USDT"`, `base` length 2-6
   - Sort by `volume_24h_quote` (or 0 if missing) descending
   - Cache for 1 hour
3. Add async method `async def search_pairs(self, query: str, limit: int = 50) -> list[dict]`:
   - Use the cached list from step 2
   - Case-insensitive substring match on `base` or `id` (`BTC_USDT`)
   - Return top `limit` by 24h volume

**API route** — `apps/api/app/api/symbols.py`:

Add the missing endpoint to the existing `router`:

```python
@router.get("/all", response_model=list[dict])
def list_all_pairs(_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """All tradable USDT pairs from configured providers, sorted by volume."""
    from app.services.market_data.factory import build_provider_for_venue
    provider = build_provider_for_venue("gateio")
    if not hasattr(provider, "get_all_spot_pairs"):
        return []
    return asyncio.run(provider.get_all_spot_pairs())  # or await it
```

Fix the existing search endpoint to also use the new full list:

```python
@router.get("/search")
def search_symbols(
    q: str = Query(min_length=1, max_length=20),
    quote: str = Query("USDT"),
    limit: int = Query(default=50, ge=1, le=200),
    _user=Depends(get_current_user),
):
    # ... use provider.search_pairs(...)
```

**Frontend** — `apps/web/lib/api.ts`:

Add to existing exports:

```ts
export type SymbolMeta = {
  id: string;          // "BTC_USDT"
  base: string;        // "BTC"
  quote: string;       // "USDT"
  venue: string;       // "gateio"
  volume_24h_quote: number;
  price?: number;
  change_24h_pct?: number;
  display: string;     // "BTC/USDT"
};

export function listAllSymbols(venue = "gateio"): Promise<SymbolMeta[]> {
  return request<SymbolMeta[]>(`/api/v1/symbols/all?venue=${venue}`);
}

export function searchSymbols(
  q: string,
  opts: { quote?: string; limit?: number } = {}
): Promise<SymbolMeta[]> {
  const params = new URLSearchParams({ q, ...opts });
  return request<SymbolMeta[]>(`/api/v1/symbols/search?${params}`);
}
```

**Verify:**
```bash
# backend tests still pass
cd apps/api && venv/Scripts/python.exe -m pytest tests/ -q
# new endpoint works
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"vfy@test.com","password":"VfyPass1!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s "http://localhost:8000/api/v1/symbols/all" \
  -H "Authorization: Bearer $TOKEN" | python -c \
  "import sys,json;d=json.load(sys.stdin);print(f'{len(d)} pairs');print([p['base'] for p in d[:10]])"
```

Expected: 200+ pairs, top 10 by volume.

---

### Task 2: Symbol browser page — `/symbols`

**Why it matters:** Right now symbol search is a tiny dropdown. A real
trading terminal has a dedicated browser with filters, sorting, and
click-to-chart.

**New files:**

```
apps/web/app/symbols/page.tsx
```

**`page.tsx` shape:**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listAllSymbols, type SymbolMeta } from "@/lib/api";

export default function SymbolsPage() {
  const [quote, setQuote] = useState("USDT");
  const [sort, setSort] = useState<"volume"|"change"|"alpha">("volume");
  const [search, setSearch] = useState("");
  const router = useRouter();

  const { data: pairs = [] } = useQuery({
    queryKey: ["all-symbols", quote],
    queryFn: () => listAllSymbols(),
  });

  const filtered = pairs
    .filter(p => p.quote === quote)
    .filter(p => !search || p.base.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sort === "volume") return b.volume_24h_quote - a.volume_24h_quote;
      if (sort === "change") return (b.change_24h_pct ?? 0) - (a.change_24h_pct ?? 0);
      return a.base.localeCompare(b.base);
    });

  return (
    <main className="p-4 max-w-7xl mx-auto">
      <h1 className="text-lg font-semibold mb-3">Symbol Browser</h1>
      <div className="flex gap-2 mb-3 flex-wrap">
        <input value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="Search by base (BTC, ETH...)"
          className="bg-panel border border-border rounded px-3 py-1.5 text-sm" />
        <select value={quote} onChange={e=>setQuote(e.target.value)}
          className="bg-panel border border-border rounded px-2 py-1.5 text-sm">
          {["USDT","USDC","BTC","ETH"].map(q=><option key={q}>{q}</option>)}
        </select>
        <select value={sort} onChange={e=>setSort(e.target.value as any)}
          className="bg-panel border border-border rounded px-2 py-1.5 text-sm">
          <option value="volume">Volume</option>
          <option value="change">24h Change</option>
          <option value="alpha">A-Z</option>
        </select>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {filtered.map(p => (
          <button key={p.id}
            onClick={() => router.push(`/terminal/${p.display}`)}
            className="bg-panel border border-border rounded p-3 text-left hover:border-info">
            <div className="font-semibold">{p.display}</div>
            <div className={`text-xs ${p.change_24h_pct && p.change_24h_pct >= 0
              ? "text-bullish" : "text-bearish"}`}>
              {p.change_24h_pct !== undefined
                ? `${p.change_24h_pct >= 0 ? "+" : ""}${p.change_24h_pct.toFixed(2)}%`
                : "—"}
            </div>
            <div className="text-[10px] text-muted">
              Vol ${(p.volume_24h_quote/1e6).toFixed(1)}M
            </div>
          </button>
        ))}
      </div>
    </main>
  );
}
```

**Update `TopNav.tsx`:** Add `{ href: "/symbols", label: "Symbols" }` between
`Analytics` and `Alerts`.

**Verify:** `npm run lint` clean, navigate to `/symbols` after `npm run dev`.

---

### Task 3: Watchlist — persistent per-user list

**Why it matters:** A terminal without a watchlist is unusable. Users
need to track symbols they care about across sessions.

**Backend change** — `apps/api/app/db/models.py`:

Add to the `Base` (before `__all__`):

```python
class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    venue: Mapped[str] = mapped_column(String(20), nullable=False, default="gateio")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("user_id", "symbol", "venue"),)
```

Also add `"WatchlistItem"` to the `__all__` list.

**New file** — `apps/api/app/api/watchlist.py`:

```python
router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])

class ItemIn(BaseModel):
    symbol: str
    venue: str = "gateio"

@router.get("")
def list_items(_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [i.symbol for i in db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == _user.id)
    ).scalars().all()]

@router.post("", status_code=201)
def add_item(body: ItemIn, _user=Depends(get_current_user), db: Session = Depends(get_db)):
    # upsert
    item = db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == _user.id,
            WatchlistItem.symbol == body.symbol,
            WatchlistItem.venue == body.venue,
        )
    ).scalar_one_or_none()
    if not item:
        item = WatchlistItem(user_id=_user.id, symbol=body.symbol, venue=body.venue)
        db.add(item); db.commit()
    return {"ok": True}

@router.delete("/{symbol}")
def remove_item(symbol: str, _user=Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == _user.id,
            WatchlistItem.symbol == symbol,
        )
    )
    db.commit()
    return {"ok": True}
```

**Register** in `main.py`:

```python
from app.api.watchlist import router as watchlist_router
app.include_router(watchlist_router)
```

**Frontend** — `apps/web/lib/api.ts`:

```ts
export function getWatchlist(): Promise<string[]> { return request("/api/v1/watchlist"); }
export function addToWatchlist(symbol: string, venue = "gateio") {
  return request("/api/v1/watchlist", { method: "POST", body: JSON.stringify({ symbol, venue }) });
}
export function removeFromWatchlist(symbol: string) {
  return request(`/api/v1/watchlist/${symbol}`, { method: "DELETE" });
}
```

**New component** — `apps/web/components/terminal/WatchlistWidget.tsx`:

A 200px-wide left rail showing the user's watchlist with a `+` button
to add the current symbol and click-to-chart.

**Verify:** `npm run lint`, open browser, add/remove symbols, refresh
page — list should persist.

---

### Task 4: Rebuild the dashboard as a real overview — TOP 25 AS CHART SOURCE

**Why it matters:** This is the most important page. Right now it's a
chart with a tiny market card. A real trading terminal dashboard has
many panels. And per your requirement — the main chart defaults to the
#1 pair by volume from the aggregate top-25 across all venues.

**New data flow:**
1. On mount, fetch `GET /api/v1/market/top?limit=25` — returns top pairs
   sorted by volume across binance/bybit/gate/kraken/okx.
2. Default the chart to the #1 pair (usually BTC/USDT from Binance).
3. Show the top-25 as a scrollable ticker strip below the chart.
4. The venue selector lets you pick which exchange's top-25 to view,
   OR "All Venues" (the aggregate).

**New frontend API** — `apps/web/lib/api.ts`:

```ts
export type TopPair = {
  id: string; base: string; display: string;
  venue: string; volume_24h_quote: number;
  price: number | null; change_24h_pct: number | null;
};

export function getTopPairs(limit = 25): Promise<{timestamp: string; top: TopPair[]}> {
  return request(`/api/v1/market/top?limit=${limit}`);
}

export function getTVPrefixes(): Promise<Record<string, string>> {
  return request("/api/v1/market/tv-prefixes");
}
```

**Dashboard layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ TOP STRIP: Market overview cards (aggregate stats)         │
│ ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐        │
│ │BTC   │ETH   │SOL   │BNB   │XRP   │ADA   │DOGE  │← top 7│
│ │$65k  │$3.5k │$145  │$580  │$0.57 │$0.42 │$0.12 │quick  │
│ │+2.3% │-1.1% │+5.2% │+0.8% │-0.3% │+1.7% │-2.1% │stats  │
│ └──────┴──────┴──────┴──────┴──────┴──────┴──────┘        │
├────────────────────────────────────────────────────────────┤
│ LEFT (20%)         │  CENTER (55%)     │ RIGHT (25%)       │
│                    │                   │                   │
│ Watchlist          │ TV chart (1h)     │ Analysis          │
│ with venue icons   │ for current sym   │ tabs for          │
│ - BTC/USDT  🟢    │                   │ current symbol    │
│ - ETH/USDT  🔵    │ Default: #1 from  │ • Gates           │
│ - + Add           │ top-25 (auto)     │ • Models          │
│                    │                   │ • History         │
│ Market Condition   │ Symbol/tf/venue   │                   │
│ (regime card)      │ bar at top        │ [Run Analysis]   │
│                    │                   │                   │
├────────────────────┴───────────────────┴──────────────────┤
│ TOP-25 TICKER STRIP (horizontal scroll)                   │
│ ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐│
│ │ #1   │ #2   │ #3   │ #4   │ #5   │... 22 more         ││
│ │BTC/US│ETH/US│SOL/US│BNB/US│XRP/US│ vol bar per card   ││
│ │✓Bin  │✓Bybit│✓OKX  │✓Gate │✓Kra │ click → chart      ││
│ └──────┴──────┴──────┴──────┴──────┴────────────────────┘│
├────────────────────────────────────────────────────────────┤
│ BOTTOM: Movers panel (24h biggest gainers/losers) + Scanner│
│ ┌───────────────────┬────────────────────────────────────┐│
│ │ Top Gainers       │  Scanner (last batch + live)       ││
│ │ +BNB +12%         │  Progress / results                ││
│ │ -DOGE -8%         │                                    ││
│ └───────────────────┴────────────────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

**The chart always uses the TV prefix.** If the current pair is
BTC/USDT on Binance, the TradingView widget loads
`BINANCE:BTCUSDT`. This works for any venue because TradingView knows
all of them.

**Verify:** Open `/dashboard`. Default chart shows top-25 #1 pair.
Click any ticker in the strip — chart switches. The top-25 refreshes
every 60s.



**Code shape (skeleton):**

```tsx
export default function DashboardPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  // existing useState for timeframe, run, analyzing, autoAnalyze

  const { data: overview } = useQuery({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 30_000,
  });

  const { data: watchlist = ["BTC/USDT","ETH/USDT","SOL/USDT"] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: getWatchlist,
  });

  return (
    <main className="p-3 flex flex-col gap-3 h-[calc(100vh-3rem)]">
      {/* TOP STRIP */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <StatCard label="BTC" value={`$${overview?.btc_price?.toFixed(0)}`}
          change={overview?.btc_change_24h} />
        <StatCard label="Market Cap" value={`$${(overview?.market_cap/1e12).toFixed(2)}T`}
          change={overview?.market_cap_change_24h_pct} />
        <StatCard label="24h Volume" value={`$${(overview?.volume_24h/1e9).toFixed(1)}B`} />
        <StatCard label="Fear & Greed" value={overview?.fear_greed ?? "—"} />
        <StatCard label="BTC Dominance" value={`${overview?.btc_dominance?.toFixed(1)}%`} />
      </div>

      {/* MAIN GRID */}
      <div className="grid grid-cols-12 gap-3 flex-1 min-h-0">
        {/* LEFT: Watchlist + Market Condition */}
        <aside className="col-span-3 flex flex-col gap-3 min-h-0">
          <WatchlistWidget onSelect={setSymbol} current={symbol} />
          <MarketConditionCard symbol={symbol} />
        </aside>

        {/* CENTER: TV Chart */}
        <section className="col-span-6 bg-panel border border-border rounded-md overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-border">
            <SymbolSearch value={symbol} onChange={setSymbol} />
            <TimeframeSelector value={timeframe} onChange={setTimeframe} />
            <label className="text-xs flex items-center gap-1">
              <input type="checkbox" checked={autoAnalyze} onChange={e=>setAutoAnalyze(e.target.checked)} />
              Auto
            </label>
          </div>
          <TradingViewChart symbol={symbol.replace("/", "")} venue={venue} interval={timeframe} />
        </section>

        {/* RIGHT: Analysis */}
        <aside className="col-span-3 flex flex-col gap-2 min-h-0 overflow-hidden">
          <AnalysisTabs run={run} isAnalyzing={analyzing}
            onRun={doAnalysis} onLoadRun={onLoadRun} />
        </aside>
      </div>

      {/* BOTTOM STRIP: Tickers + Movers */}
      <div className="grid grid-cols-2 gap-3 h-48">
        <TickerGrid tickers={overview?.tickers ?? []} onSelect={setSymbol} />
        <MoversPanel movers={overview?.movers ?? []} onSelect={setSymbol} />
      </div>
    </main>
  );
}

function StatCard({ label, value, change }: ...) {
  return (
    <div className="bg-panel border border-border rounded-md px-3 py-2">
      <div className="text-[10px] text-muted uppercase">{label}</div>
      <div className="text-lg font-bold">{value}</div>
      {change !== undefined && (
        <div className={`text-xs ${change >= 0 ? "text-bullish" : "text-bearish"}`}>
          {change >= 0 ? "+" : ""}{change.toFixed(2)}%
        </div>
      )}
    </div>
  );
}
```

**`getMarketOverview` already exists** in `lib/api.ts`. Check the
current shape — the top strip maps the fields it returns. If
`fear_greed` doesn't exist yet, add it to the backend
`overview` route as a constant (e.g. `"Greed"` or read from a public
API like `https://api.alternative.me/fng/` — cache 1 hour).

**Verify:** Open `/dashboard`. All 5 panels render. Click a watchlist
item — chart updates. Click "Run Analysis" — right panel populates.

---

### Task 5: Populate the `/alerts` page

**Why it matters:** Right now `/alerts` only shows the list with no way
to create alerts. Users should be able to build price/gate/indicator
alerts visually.

**New component** — `apps/web/components/alerts/AlertBuilder.tsx`:

A form with: symbol picker (uses `listAllSymbols`), condition type
dropdown (price above/below, gate score, indicator), value input,
channels, cooldown, "Save" button.

**Backend** — `apps/api/app/api/alerts.py`: extend the existing
`AlertCreate` model + add `PUT` update + `DELETE` endpoints. Reuse the
`Alert` DB model.

**Modify** `apps/web/app/alerts/page.tsx`: add a tab bar at the top —
`Active | History | + New`. The "New" tab embeds `<AlertBuilder/>`.

**Verify:** Build an alert, refresh page, alert still there.

---

### Task 6: Make `/analytics` look like a real performance page

**Why it matters:** Right now the page is a grid of small numbers. A
trading performance page has charts.

**Modify** `apps/web/app/analytics/page.tsx` to include:

1. **Equity curve** — line chart (use a lightweight inline SVG or
   `recharts` if installed; check `package.json` first. If not
   installed, add it: `npm install recharts`).
2. **Monthly returns heatmap** — 12-cell grid, green for positive,
   red for negative, intensity by magnitude.
3. **Win rate gauge** — circular progress (SVG arc).
4. **Top winners/losers** — table sorted by PnL.
5. **Drawdown chart** — line chart of running max minus current.

The `TradeAnalytics` dataclass in `app/services/analytics/trade_analytics.py`
already computes these values; expose them through the API or compute
client-side from `/api/v1/analytics/equity-curve` and
`/api/v1/analytics/by-symbol`.

**Add to backend** `apps/api/app/api/analytics.py`:

```python
@router.get("/drawdown")
def drawdown_curve(_user=..., db=...):
    stats = compute_overview(db, _user.id)
    peak = float("-inf")
    dd = []
    for v in stats.equity_curve:
        peak = max(peak, v)
        dd.append(round(peak - v, 2))
    return {"drawdown": dd}

@router.get("/top-movers")
def top_movers(_user=..., db=...):
    stats = compute_overview(db, _user.id)
    by_pnl = sorted(stats.by_symbol, key=lambda x: -x["pnl"])
    return {"winners": by_pnl[:5], "losers": by_pnl[-5:]}
```

**Verify:** `npm run lint` clean, navigate to `/analytics`, all
sections render even with empty data (show `—` placeholders).

---

### Task 7: Journal page — filters + PnL chart

**Why it matters:** Right now `/journal` lists entries with no
insight. A journal page should be a sortable, filterable ledger.

**Modify** `apps/web/app/journal/page.tsx`:

1. Add filter bar: symbol dropdown, side (LONG/SHORT), status (open/closed).
2. Add sortable columns: opened_at, symbol, side, qty, entry, exit, pnl.
3. Show summary stats at top: total trades, win rate, total PnL, avg
   hold time.
4. Add an "Export CSV" button that downloads current filtered list.

**New helper** in `lib/api.ts`:

```ts
export function exportJournalCSV(filters: Record<string, string>): string {
  const params = new URLSearchParams(filters);
  return `${API_BASE}/api/v1/journal/export?${params}`;
}
```

**Backend** — `apps/api/app/api/journal.py`: add `GET /export` that
streams a CSV.

**Verify:** `npm run lint` clean, open `/journal`, filter by BTC,
see only BTC entries, click export, CSV downloads.

---

### Task 8: Scanner page — live progress

**Why it matters:** Currently `app/scan/page.tsx` triggers a scan but
the progress UI is basic. Real scanners show per-symbol progress
inline.

**Modify** `apps/web/app/scan/page.tsx`:

- Live progress bar per symbol (queued → running → done/failed)
- Per-symbol result card: final state, composite score, top gates
- Click result → opens that symbol's terminal
- Cancel button to abort the batch

Use the existing `/api/v1/scanner/start` and `/api/v1/scanner/status`
endpoints. Add a new endpoint if needed:

```python
@router.get("/batch/{batch_id}/results")
def batch_results(batch_id: str, ...):
    """Return per-symbol results for a running/completed batch."""
```

**Verify:** Trigger a scan, watch progress update in real time, click
a result to open the chart.

---

### Task 9: Add a `/backtest` page

**Why it matters:** Backtest engine exists in `engine/backtest/` but
no UI. Right now you can't run a backtest from the app.

**New file** — `apps/web/app/backtest/page.tsx`:

Form: symbol, timeframe, date range, strategy preset, initial balance.
On submit, call backend to run (synchronous for now — engine returns
fast enough). Display: equity curve, metrics grid, trade list.

**Backend route** — `apps/api/app/api/backtest.py`:

```python
router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

class BacktestIn(BaseModel):
    symbol: str
    timeframe: str
    strategy: str = "balanced"
    start_date: str  # ISO
    end_date: str
    initial_balance: float = 10000.0
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0

@router.post("/run")
async def run_backtest_endpoint(body: BacktestIn, _user=..., db=...):
    # fetch candles from provider
    provider = build_provider()
    candles = await provider.get_ohlcv(body.symbol, body.timeframe, limit=2000)
    # signal function — for now, use a simple momentum cross
    async def signal(window): return {"action": "BUY"} if window[-1].close > window[-20].close else {"action": "SELL"}
    from app.engine.backtest.backtest_runner import run_backtest
    metrics = await run_backtest(candles, signal, initial_balance=body.initial_balance)
    return metrics.__dict__
```

**Verify:** Run a backtest for BTC/USDT 1h, last 7 days. Metrics
panel populates.

---

### Task 10: Settings page improvements

**Modify** `apps/web/app/settings/page.tsx`:

1. Add a "Strategy Templates" section — call
   `GET /api/v1/strategies/templates` (or just hardcode the 5 templates
   from `engine/strategy_templates.py`), show as cards. Click "Apply" to
   activate one.
2. Add a "Risk Limits" section — input fields for risk_per_trade_pct,
   daily_max_loss_pct, etc. Persist via `PUT /api/v1/risk/config`
   (you may need to add this endpoint).
3. Add a "Reset" button that wipes all user data (trades, journal,
   alerts) — confirm dialog before calling `POST /api/v1/user/reset`.

**Verify:** `npm run lint` clean. Apply a template, see it reflected
in the next analysis run.

---

### Task 11: Polish — keyboard shortcuts, toaster, skeletons, theming

This is the pass that makes it feel like a real terminal.

**11a — Global keyboard shortcuts:**

New component `apps/web/components/terminal/KeyboardShortcuts.tsx`
mounted in `app/layout.tsx`:

- `/` — focus symbol search
- `g d` — go to dashboard
- `g t` — go to terminal (last viewed symbol)
- `g s` — go to scanner
- `g a` — go to analytics
- `g j` — go to journal
- `?` — show shortcut help modal
- `Esc` — close any open modal

**11b — Notification toaster:**

New component `apps/web/components/Toast.tsx`. Listens to the
WebSocket `/ws/{token}` endpoint (already exists). On
`analysis_complete`, show a toast: "BTC/USDT analysis: LONG_CANDIDATE
(composite +0.67)". On `alert_fired`, show: "[CRITICAL] High volatility
detected".

**11c — Loading skeletons:**

Every page that calls `useQuery` should show a skeleton while
`isLoading`. Add `apps/web/components/ui/Skeleton.tsx` (just a pulsing
gray div) and use it in each page.

**11d — Visual depth:**

Update `app/globals.css`:
- Add `--color-panel-2: #1a2030;` (slightly lighter for elevated panels)
- Add `box-shadow: 0 2px 8px rgba(0,0,0,0.3);` to `.bg-panel` cards
- Add `backdrop-filter: blur(8px);` to the top nav

**11e — Empty-state illustrations:**

New component `apps/web/components/ui/EmptyState.tsx`:

```tsx
export function EmptyState({ title, hint, action }: {
  title: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="text-4xl mb-2 opacity-30">📊</div>
      <div className="text-sm font-semibold text-muted">{title}</div>
      {hint && <div className="text-xs text-muted mt-1">{hint}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
```

Use in `/alerts`, `/journal`, `/analytics` instead of "no data yet"
text.

**Verify:** `npm run lint` clean. Press `/` — search box focuses.
Trigger an analysis run — toast appears in the corner. Empty pages
show the empty state, not raw text.

---

## Out of scope (explicit)

Don't touch these in this pass — they're separate future plans:

- DEX support (Uniswap v3, GMX, Jupiter) — interface exists, adapters don't
- Live WebSocket price ticks — TV widget handles its own; we don't need to duplicate
- Drawing tools persistence (TV's paid feature or custom impl)
- Mobile-specific layout (the grid is already responsive enough)
- Auth: add OAuth (Google/Discord) — separate task
- Notifications: SMS/email/Telegram/Discord dispatch (Phase 15 backend)
  — the alert engine exists, the dispatcher doesn't yet
- Adding more venues (Coinbase, KuCoin, HTX, Mexc, Bitget) — interface
  pattern is established; they're a 1h copy-paste each

## What's already done (don't rebuild)

| Item | Status | Files |
|------|--------|-------|
| 6 venue providers | ✅ Built and registered | `binance_rest.py`, `bybit_rest.py`, `kraken_rest.py`, `okx_rest.py`, `gateio_rest.py`, `registry.py` |
| Top-25 aggregate endpoint | ✅ Built | `apps/api/app/api/aggregate.py` |
| TV prefix map endpoint | ✅ Built | `GET /api/v1/market/tv-prefixes` |
| Symbol all/search on all venues | ✅ Built | Each provider has `get_all_spot_pairs()` + `search_pairs()` |
| Gate.io full pair listing | ✅ Built | `gateio_rest.py` now has `get_all_spot_pairs()` |
| Progress changelog | ✅ Built | `docs/progress/2026-07-19-ui-repair.md` |

---

## Definition of done

- `cd apps/api && venv/Scripts/python.exe -m pytest tests/ -q` → 81+
  passed
- `cd apps/web && npm run lint` → 0 errors
- All 11 tasks above implemented
- No new TypeScript `any` (use real types)
- No file > 400 lines (split if it grows)
- Every page handles its empty state via `<EmptyState/>`
- The dashboard at `/` looks like a real trading terminal, not a
  blank chart page
- All existing 81 backend tests still pass

---

## Per-task budget

| Task | Effort | Risk |
|------|--------|------|
| 1 — Full pair coverage | 2h | Low |
| 2 — Symbol browser | 1.5h | Low |
| 3 — Watchlist | 1.5h | Med (DB schema) |
| 4 — Dashboard rebuild | 4h | Med (lots of pieces) |
| 5 — Alerts UI | 2h | Med |
| 6 — Analytics charts | 2h | Med (recharts or inline SVG) |
| 7 — Journal filters | 1.5h | Low |
| 8 — Scanner progress | 1.5h | Low |
| 9 — Backtest page | 2.5h | Med |
| 10 — Settings | 1.5h | Low |
| 11 — Polish | 2h | Low |
| **Total** | **~22h** | |

A cheaper model executing in order should finish this in one focused
session.
