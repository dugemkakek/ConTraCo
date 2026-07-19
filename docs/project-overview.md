# Confluence Trading Consultant — Project Overview

> **Stack:** Python 3.14 + FastAPI backend · Next.js 16 + React 19 + Tailwind frontend  
> **Charts:** TradingView Advanced Chart widget (CDN) + lightweight-charts (sparklines)  
> **AI:** Mineral (ocg/minimax-m3 via InferHub) council of 6 roles + 6 gates  
> **Data:** Mock provider (dev) · Gate.io REST + WS (live) — abstracted for multi-venue

---

## Project Layout

```
F:\Programs\confluence-trading-consultant\
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py          # Entry: lifespan, CORS, 9 routers registered
│   │   │   ├── api/             # Route handlers
│   │   │   │   ├── auth.py      # POST /register, /login, /me
│   │   │   │   ├── market_data.py  # GET /market-data/{sym}/candles, /stream (SSE)
│   │   │   │   ├── analysis.py  # POST /analysis/run, GET /analysis/runs, /runs/{id}
│   │   │   │   ├── symbols.py   # GET /symbols, /symbols/search, /symbols/venues, POST /symbols/sync
│   │   │   │   ├── scanner.py   # POST /scanner/run, GET /scanner/status, /scanner/latest
│   │   │   │   ├── overview.py  # GET /market-overview
│   │   │   │   ├── strategy.py  # CRUD strategy configs
│   │   │   │   ├── journal.py   # CRUD trade journal entries
│   │   │   │   ├── trades.py    # Paper orders + config
│   │   │   │   └── deps.py      # get_current_user, get_admin_user
│   │   │   ├── services/
│   │   │   │   ├── market_data/  # Provider abstraction layer
│   │   │   │   │   ├── base.py         # MarketDataProvider Protocol
│   │   │   │   │   ├── registry.py     # Venue registry (mock, gateio)
│   │   │   │   │   ├── factory.py      # build_provider(), build_provider_for_venue()
│   │   │   │   │   ├── mock_provider.py # Deterministic sine-wave generator (dev/CI)
│   │   │   │   │   ├── gateio_rest.py  # Gate.io REST OHLCV + spot pairs
│   │   │   │   │   └── gateio_ws.py    # Gate.io WebSocket live candle stream
│   │   │   │   ├── llm/                # LLM brain
│   │   │   │   │   ├── __init__.py     # OpenAICompatClient, StubClient, current_provider()
│   │   │   │   │   ├── compression.py  # Auto-compress at 100k tokens
│   │   │   │   │   └── prompts.py      # Council role prompts
│   │   │   │   └── execution/          # (future) Live execution
│   │   │   ├── engine/                 # Trading analysis engine
│   │   │   │   ├── council.py          # 6-role LLM council orchestrator
│   │   │   │   ├── decision.py         # Composite scoring + veto logic
│   │   │   │   ├── gates/              # 6 gate evaluators
│   │   │   │   │   ├── market_regime.py, market_structure.py
│   │   │   │   │   ├── volume_momentum.py, classical_ta.py
│   │   │   │   │   ├── risk_tradeability.py, fundamental_context.py
│   │   │   │   ├── runner.py           # Orchestrates analysis run
│   │   │   │   ├── strategy.py         # Strategy configuration
│   │   │   │   └── trade_plan.py       # Trade plan generation
│   │   │   ├── schemas/                # Pydantic models
│   │   │   │   ├── candle.py           # Candle, CandleResponse
│   │   │   │   └── overview.py         # MarketOverview, TickerSnapshot, Breadth, Movers
│   │   │   ├── db/                     # SQLite (dev) / Postgres (prod)
│   │   │   │   ├── models.py           # 11 tables: User, AnalysisRun, Decision, GateResult,
│   │   │   │   │                       #   ModelOpinion, TradePlan, JournalEntry, Order,
│   │   │   │   │                       #   StrategyConfig, SymbolMeta, Alert
│   │   │   │   ├── redis_client.py     # In-proc shim or real Redis
│   │   │   │   └── __init__.py         # get_db, get_engine, migrations
│   │   │   ├── indicators.py           # TA functions (tech indicators)
│   │   │   └── security.py             # JWT encode/decode
│   │   ├── tests/                      # 58+ tests
│   │   │   ├── test_api.py, test_council.py, test_decision.py
│   │   │   ├── test_gates.py, test_overview.py, test_venues.py
│   │   │   ├── test_compression.py, test_council_parsers.py
│   │   │   ├── test_mock_candles.py
│   │   │   └── conftest.py
│   │   └── apps/api/.env               # LLM_API_KEY, MARKET_DATA_PROVIDER
│   │
│   └── web/                    # Next.js frontend
│       ├── app/
│       │   ├── (auth)/login/   & register/     — Login/register forms
│       │   ├── terminal/[symbol]/page.tsx       — Trading terminal (TV chart + analysis panel)
│       │   ├── dashboard/page.tsx               — Full trading terminal layout (chart + stats)
│       │   ├── scan/page.tsx                    — Multi-symbol scanner status + results
│       │   ├── journal/page.tsx                 — Trade journal CRUD
│       │   └── settings/page.tsx                — Strategy config management
│       ├── components/
│       │   ├── chart/
│       │   │   ├── TradingViewChart.tsx         — TV Advanced Chart widget (primary chart)
│       │   │   └── CandlestickChart.tsx         — Lightweight-charts (fallback, kept for sparklines)
│       │   ├── terminal/
│       │   │   ├── TopNav.tsx                   — Navigation bar
│       │   │   ├── TimeframeSelector.tsx        — 1m/5m/15m/1h/4h/1d selector
│       │   │   ├── SymbolSearch.tsx             — Debounced symbol search (cross-venue)
│       │   │   ├── VenueSelector.tsx            — Venue dropdown from /venues
│       │   │   └── DataFreshnessBadge.tsx       — Data freshness indicator
│       │   ├── decision/
│       │   │   ├── AnalysisTabs.tsx             — Tabbed container (Analysis / Details / History)
│       │   │   ├── DecisionConsole.tsx          — Final state + composite score display
│       │   │   ├── TradePanel.tsx               — Trade plan summary
│       │   │   ├── TradePlanDetail.tsx          — Full trade plan grid
│       │   │   ├── GateScores.tsx               — Gate bars with thresholds
│       │   │   ├── ModelOpinions.tsx            — Council opinions table
│       │   │   ├── RiskFlags.tsx                — Risk flags + vetoes
│       │   │   └── RunHistory.tsx               — Past analysis runs
│       │   └── dashboard/
│       │       ├── MarketConditionCard.tsx       — RISK-ON/OFF/MIXED verdict
│       │       ├── BreadthGauge.tsx             — Stacked bar (up/flat/down)
│       │       ├── MoversPanel.tsx              — Top gainers/losers
│       │       ├── TickerGrid.tsx               — Symbol cards with sparklines
│       │       └── Sparkline.tsx                — Inline SVG mini-chart
│       ├── lib/
│       │   ├── api.ts                   — All API client functions + types
│       │   ├── auth-context.tsx         — Auth provider + useAuth hook
│       │   ├── query-client.tsx         — React Query provider
│       │   ├── analysis-store.ts        — Zustand store for analysis state
│       │   └── indicators.ts            — EMA computation
│       └── tests/
│           ├── terminal.spec.ts         — 3 E2E tests (auth gate, chart load, analysis)
│           └── dashboard.spec.ts        — 1 E2E test (layout + search)
│
├── HANDOFF.md                    # Source-of-truth handoff doc (updated per phase)
├── docs/plans/                   # Implementation plans for future phases
└── docker-compose.yml            # Full-stack Docker deployment

```

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Create user account |
| POST | `/api/v1/auth/login` | Login → JWT token |
| GET | `/api/v1/auth/me` | Current user info |

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/market-data/{symbol}/candles` | OHLCV candles (timeframe, limit) |
| GET | `/api/v1/market-data/{symbol}/stream` | SSE live candle updates |
| GET | `/api/v1/market-overview` | Aggregated market overview (breadth, movers, tickers with RSI/trend/sparkline) |

### Symbols & Venues
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/symbols` | List symbols (from DB or provider) |
| GET | `/api/v1/symbols/venues` | List configured venues |
| GET | `/api/v1/symbols/search?q=` | Cross-venue symbol search |
| POST | `/api/v1/symbols/sync` | Sync Gate.io spot pairs into DB |

### Analysis
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/analysis/run` | Run council analysis (symbol, timeframe, strategy) |
| GET | `/api/v1/analysis/runs` | List past runs (by symbol, limit) |
| GET | `/api/v1/analysis/runs/{id}` | Get specific analysis run |

### Scanner
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/scanner/run` | Run scanner across universe |
| GET | `/api/v1/scanner/status` | Current scan status + notable results |
| GET | `/api/v1/scanner/latest` | Latest scan results |

### Strategy
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/strategies/active` | Active strategy config |
| GET | `/api/v1/strategies` | List all strategy configs |
| POST | `/api/v1/strategies` | Create strategy config |

### Journal & Trades
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/journal` | List journal entries (filter by symbol, open_only) |
| POST | `/api/v1/journal` | Create journal entry |
| POST | `/api/v1/journal/{id}/close` | Close journal entry |
| DELETE | `/api/v1/journal/{id}` | Delete journal entry |
| GET | `/api/v1/journal/summary` | Journal stats (PnL, win rate) |
| GET | `/api/v1/trades/config` | Paper trading config |
| POST | `/api/v1/trades/orders` | Place paper order |
| GET | `/api/v1/trades/orders` | List paper orders |

### Health
| GET | `/health` | Server health + provider info |

---

## Core Architecture

### Analysis Pipeline
```
User clicks "Analyze" (or auto-analyze fires)
  → POST /api/v1/analysis/run { symbol, timeframe }
    → runner.py fetches OHLCV from provider (mock / gateio)
    → 6 gates evaluate (market_regime, structure, volume, TA, risk, fundamental)
    → 6 LLM council roles evaluate (technical, momentum, market_context,
       fundamental, risk_reviewer, skeptical) — each calls LLM via OpenAICompatClient
    → decision.py composites gate + model scores with veto logic
    → trade_plan.py generates trade plan if score > threshold
    → Stored in DB (AnalysisRun + GateResult + ModelOpinion + Decision + TradePlan)
    → Returns full RunOut JSON
```

### Market Data Flow
```
Provider Registry (mock, gateio)
  → GET /api/v1/market-data/{symbol}/candles
    → build_provider() or build_provider_for_venue(venue_id)
    → provider.get_ohlcv(symbol, timeframe, limit)
    → Returns CandleResponse

Streaming:
  → GET /api/v1/market-data/{symbol}/stream (SSE)
    → CandleStream.subscribe(symbol, timeframe)
    → Pushes real-time candle updates via WebSocket → SSE bridge
```

### Multi-Venue Architecture
```
registry.py holds _VENUE_REGISTRY = { "mock": MockMarketDataProvider, "gateio": GateioRestProvider }
  → list_venues() returns active venues
  → get_provider(venue_id) returns specific provider
  → all_providers() iterates all venues for search

TradingViewChart.tsx maps venue → TV prefix:
  gateio → GATEIO:BTCUSDT
  binance → BINANCE:BTCUSDT  (scaffolded, not implemented)
  mock → GATEIO (fallback)
```

### Database Schema (SQLite / Postgres)
```
User(id, email, password_hash, is_admin, is_active, created_at)
StrategyConfig(id, name, version, payload JSON, is_active, created_at)
AnalysisRun(id, user_id, symbol, timeframe, status, final_state, config_id, started_at, completed_at, note)
Decision(id, run_id, final_state, gate_score, model_score, composite_score, model_agreement, data_completeness, model_completeness, vetoes, veto_sources, reason)
GateResult(id, run_id, gate_name, status, score, weight, confidence, reason, evidence JSON)
ModelOpinion(id, run_id, role, status, direction, confidence, role_weight, confidence_cap, reason, risk_flags, evidence_ids, raw_output JSON)
TradePlan(id, run_id, direction, entry_price, stop_price, take_profit, risk_reward, position_size_pct, invalidation, risk_review, synthesis)
JournalEntry(id, user_id, symbol, side, entry_price, exit_price, qty, opened_at, closed_at, pnl, notes, analysis_run_id)
Order(id, user_id, exchange, symbol, side, order_type, qty, price, status, exchange_order_id, created_at, submitted_at, filled_at, raw_response JSON)
SymbolMeta(id, symbol, exchange, base, quote, is_active, tick_size, min_qty, last_synced)
Alert(id, user_id, symbol, severity, message, is_read, created_at)
```

---

## Frontend Pages

| Route | Description | Auth |
|-------|-------------|------|
| `/` | Landing → redirects to /terminal or /login | No |
| `/login` | Login form | No |
| `/register` | Registration form | No |
| `/terminal/[symbol]` | Trading terminal with TV chart + analysis panel | Yes |
| `/dashboard` | Full trading terminal layout (chart 70% + analysis 30% + bottom stats) | Yes |
| `/scan` | Multi-symbol scanner page with live status | Yes |
| `/journal` | Trade journal listing + CRUD | Yes |
| `/settings` | Strategy config management | Yes |

---

## What's Working (Phase 1-9)

1. **User auth** — Register/login with JWT, auth gate on all pages
2. **TradingView chart** — Full Advanced Chart widget on terminal + dashboard (dark theme, MAs, RSI)
3. **Multi-venue support** — Venue registry + symbol search across venues
4. **Analysis engine** — 6 gates + 6 LLM council roles → composite score → trade plan
5. **Auto-analysis** — Toggle to automatically analyze on symbol/timeframe change
6. **Complete stats** — Tabbed side panel (analysis, gate scores, model opinions, risk flags, history)
7. **Market overview** — Dashboard with RSI, trend, sparklines, breadth, movers
8. **Scanner** — Batch scan all symbols with real-time status
9. **Trade journal** — Manual entry with PnL tracking
10. **Paper trading** — Place orders via Gate.io paper API
11. **Mock provider** — Deterministic OHLCV generator for dev/CI
12. **Gate.io provider** — Real REST + WebSocket data (set `MARKET_DATA_PROVIDER=gateio`)
13. **Auto-compress** — LLM context compression at 100k tokens for long sessions
14. **Stub client** — Offline fallback when no LLM API key is set
15. **Test count** — 58 backend tests, web tsc clean, 5 e2e tests

---

## What's NOT Built (Future Phases)

- **Binance/Bybit/OKX providers** — Registry pattern is ready, just need to implement the REST adapter
- **DEX providers** — Uniswap v3 via TheGraph, GMX, etc. — same interface, new adapter
- **Real-time dashboard WebSocket** — Currently polling every 30s
- **Drawing tools persistence** — TV widget has drawings but persistence requires paid TV features
- **Live trading** — Paper mode only; live mode exists in code paths but never tested
- **Order book / depth chart** — TV widget can show depth but needs configuration
- **Multi-chart layout** — Side-by-side pairs, correlation view
- **Backtesting engine** — Historical strategy simulation
- **Mobile responsive** — Responsive layout exists but mobile UX not optimized
- **Performance mode** — Auto-switch between scalp/swing strategies (design exists, not built)

---

## Key Env Vars

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_API_KEY` | InferHub API key for LLM council | (stub mode) |
| `LLM_PROVIDER` | LLM provider name | `ocg` |
| `MARKET_DATA_PROVIDER` | `mock` or `gateio` | `mock` |
| `LIVE_TRADING` | `0` = paper, `1` = live (untested) | `0` |

---

## How to Run

```bash
# Backend
cd apps/api
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend
cd apps/web
npm run dev

# Tests
cd apps/api
venv\Scripts\python.exe -m pytest tests/ -q

cd apps/web
npm run lint
npx playwright test --reporter=list
```
