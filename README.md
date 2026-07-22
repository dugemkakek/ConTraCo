# ConTraCo — Confluence Trading Consultant

**Stop guessing. Start deciding with evidence.**

ConTraCo is an institutional-grade crypto trading terminal that fuses 14
deterministic analysis gates, a 6-agent AI debate council, and a 7-stage
decision engine into one clear call: **LONG / SHORT / WAIT / AVOID**.

You always pull the trigger. ConTraCo hands you the loaded weapon.

> Decision support only — human approval required. Not financial advice.

---

## Why ConTraCo

| Problem | ConTraCo |
|---|---|
| 17 indicators, no consensus | 14 gates scored, weighted, regime-adjusted → single confluence score |
| AI hallucinates confidence | Spec-enforced `confidence_cap` + `role_weight` — the AI can't over-assert |
| Backtests lie | Walk-forward split, per-gate accuracy, no-lookahead engine |
| One timeframe = tunnel vision | Multi-Timeframe Confluence: HTF/MTF/LTF alignment in one run |
| "Where are the stops?" | Liquidity heatmaps, funding/OI, orderbook depth — all in the chart rail |
| Position sizing is a coin flip | Kelly Criterion `f* = (bp - q) / b` with N≥30 sample gate |

---

## Features

### 14 Deterministic Gates
Classical TA · Market Regime · Market Structure (SMC) · Volume & Momentum ·
Ichimoku Cloud · Fibonacci Levels · Funding Rate · Orderbook Micro ·
Liquidity Heatmap · Pattern Recognition · On-Chain Flow · Fundamental Context ·
Risk & Tradeability · Market Structure (swing BOS/CHoCH)

Each gate returns a score [-100, 100], confidence, direction, and evidence.
Weights are strategy-configurable. Regime-aware multipliers adapt to
trending vs. ranging vs. volatile markets.

### AI Debate Council (6 Roles)
Technical Analyst · Market Context Analyst · Risk Reviewer · Skeptical
Reviewer · Trade Planner · Synthesis Reviewer.

Powered by any OpenAI-compatible LLM (default: InferHub). Spec-defined
caps prevent any single role from dominating. Risk flags carry veto power.
Falls back to a deterministic stub when offline — the terminal never breaks.

### Multi-Timeframe Confluence (MTC)
Run the full 14-gate pipeline across HTF/MTF/LTF simultaneously.
Timeframe-weighted alignment score. +12% MTC bonus when all three agree.

### Confluence Engine
`C_total = (Σ(w_eff × d × c) / Σ w_eff) × 100`

Score bands: ≥75 Strong · 50–74 Moderate · <50 Divergent.
Scenario framing: primary / alternative / invalidation paths.

### Backtest Engine
Event-driven, no-lookahead, walk-forward. Uses the **real** 14-gate
confluence signal — not a placeholder. Per-gate accuracy tracking.
Equity curve + benchmark curve. Configurable fees, slippage, holding period.

### Kelly Criterion Position Sizing
`f* = (bp - q) / b` — optimal bet sizing from historical win rate and
setup R:R. N≥30 sample gate prevents overfitting on thin data.

### Multi-Venue Market Data
Binance · Gate.io · Bybit · Kraken · OKX — real public candles, no API key.
Venue registry with symbol search across all exchanges.

### Liquidity & Derivatives
Funding rates (current, predicted, annualized) · Open Interest + 24h change ·
Long/Short ratio · Liquidation cluster heatmaps · Orderbook depth & imbalance.

### Delta-Neutral Yield & Arbitrage Scanner
CEX/DEX spread matrix · Funding rate opportunities · Cross-venue yield table.

### On-Chain & Whale Tracking
Exchange net flows · Whale wallet movements · 8th gate integration.

### Trading Journal + P&L Attribution
Manual + auto-created entries · Close with exit price · Summary stats ·
P&L attribution by gate — know which signals actually make money.

### Risk Engine
Risk-of-ruin calculator · Drawdown guard · Portfolio exposure tracking.

### Auth & Execution
JWT + bcrypt · Paper trading by default · Live execution with HMAC-signed
orders (Gate.io) · Per-order notional cap · CORS lockdown.

---

## Seven Workspaces

| Workspace | What it does |
|---|---|
| **Mission Control** | Market condition, breadth gauge, movers, ticker grid |
| **Charting** | TradingView + Lightweight Charts, liquidity heatmap, funding/OI, orderbook |
| **Debate Chamber** | Confluence verdict, bull/bear/neutral camps, 14-gate matrix, Kelly sizing |
| **Strategy Lab** | Backtest controls, equity curve, metric grid, run history |
| **Journal** | Trade log, P&L summary, gate attribution |
| **Arbitrage** | Funding/yield opportunities, CEX/DEX spread matrix |
| **Settings** | Versioned strategy editor, gate weights, presets |

Plus: Terminal, Scanner, Analytics, Alerts as secondary views.

---

## Quick Start

### Docker
```bash
cp .env.example .env
docker compose up --build
```

### Local (no Docker)
```bash
# API
cd apps/api
python -m venv venv && venv/Scripts/activate   # or source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Web
cd apps/web
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

- Web: http://localhost:3000
- API: http://localhost:8000/health
- Docs: http://localhost:8000/docs

Default admin: `admin@example.com` / `ChangeMe123!` (set `SEED_ADMIN=1`).

### LLM Brain (optional)
```bash
# .env in apps/api/
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.inferhub.dev/v1
LLM_MODEL=ocg/minimax-m3
```
Without a key, the deterministic stub keeps everything runnable offline.

---

## Architecture

```
Next.js 16 (React 19, Turbopack)
   │  JWT in localStorage · React Query · TradingView + Lightweight Charts
   ▼
FastAPI ──► SQLAlchemy 2 ──► Postgres / SQLite
       └──► Redis (or in-proc shim) for pub/sub
       └──► Multi-venue REST + WebSocket for market data
       └──► 14 gates → Confluence engine → AI council → Decision engine
```

## Tests

```bash
cd apps/api && pytest -q          # 107 tests
cd apps/web && npm run build      # 16 routes, typecheck + bundle
```

## Repo Layout

```
apps/
├── api/                    # FastAPI monolith
│   ├── app/
│   │   ├── api/               # HTTP routers (20+ endpoints)
│   │   ├── db/                # SQLAlchemy models, Redis client
│   │   ├── engine/            # Gates, confluence, council, debate,
│   │   │                      # decision, backtest, MTC, risk, scheduling
│   │   ├── schemas/           # Pydantic shapes
│   │   └── services/          # Market data (5 venues), LLM, execution,
│   │                          # arbitrage, fundamentals, on-chain
│   └── tests/                 # 107 tests
└── web/                    # Next.js 16 App Router
    ├── app/                   # 16 routes (7 workspaces + auth + secondary)
    ├── components/            # Chart, decision, terminal, dashboard
    └── lib/                   # API client, auth, indicators

packages/strategy-presets/     # aggressive, balanced, conservative
docs/                          # architecture, decision-engine, data-contracts
```

## Security

- Live trading gated by `LIVE_TRADING=1` + per-order notional cap
- No exchange private keys read until live flag is on
- JWT HS256 + bcrypt — rotate `JWT_SECRET` before any non-local deploy
- CORS lockdown via `CORS_ORIGINS`
- See [`docs/threat-model.md`](docs/threat-model.md)

---

## License

Private. All rights reserved.
