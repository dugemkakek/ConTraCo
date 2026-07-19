# Confluence Trading Consultant

AI-assisted, human-decides crypto trading terminal. Deterministic gates
plus an AI council, balanced through a 7-stage decision engine, surface a
clear **LONG / SHORT / WAIT / AVOID** call for every (symbol, timeframe)
pair. The trader always pulls the trigger — the system only recommends.

> Decision support only — human approval required. Not financial advice.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Web:  http://localhost:3000/terminal/BTC-USDT
- API:  http://localhost:8000/health
- API docs: http://localhost:8000/docs

A default admin account is created on first boot from
`$ADMIN_EMAIL` / `$ADMIN_PASSWORD` (defaults `admin@example.com` /
`ChangeMe123!`). Register more users via `POST /api/v1/auth/register`
or the `/register` UI page.

## Quick start (no Docker, local Postgres + SQLite)

The API works without containers. `DATABASE_URL` defaults to a
SQLite file in the API directory if unset, and `REDIS_URL` falls
back to an in-process pub/sub shim when no Redis is reachable.

```bash
# API
cd apps/api
pip install -r requirements.txt
pytest -q                                     # 30 tests
uvicorn app.main:app --reload --port 8000

# Web (separate terminal)
cd apps/web
npm install
npm run build
npm start                                      # production on :3000
# or for dev with HMR
npm run dev
```

## Architecture

```
Next.js 15 (terminal, scanner, journal, settings, auth)
   │  Bearer token in localStorage; SSE for live candles
   ▼
FastAPI ──► SQLAlchemy 2 ──► Postgres (history, users, gates, runs, trades)
       └──► Redis (or in-proc shim) for candle fan-out + scan alerts
       └──► Gate.io REST + WebSocket (or Mock fixture) for market data
       └──► Deterministic gates + AI council + decision engine
```

See [`docs/architecture.md`](docs/architecture.md) for module breakdown and
[`docs/decision-engine.md`](docs/decision-engine.md) for the full 7-stage
pipeline spec.

## What's in the box

### Phase 0 + 1 (scaffold) — done
- Docker Compose with web, api, postgres, redis.
- FastAPI `/health` and `GET /api/v1/market-data/{symbol}/candles`.
- Next.js terminal page with `lightweight-charts` and EMA 20/50/200 overlay.

### Phase 2 — done
- 6 deterministic gates: `market_regime`, `classical_ta`,
  `market_structure`, `volume_momentum`, `fundamental_context`,
  `risk_tradeability`. Each is unit-tested.
- Real **Gate.io spot REST + WebSocket** adapter, env-switched against
  the deterministic mock. The chart subscribes via `EventSource` and
  mutates the last bar in place.
- `AnalysisRun`, `GateResult`, `ModelOpinion`, `Decision`, `TradePlan`
  persisted to Postgres via SQLAlchemy 2 + Alembic migrations.
- `SymbolMeta` synced from Gate.io's `/spot/currency_pairs`.

### Phase 3 — done
- Versioned, audit-trailed `StrategyConfig` with three built-in
  presets (aggressive, balanced, conservative) and a UI editor at
  `/settings`.
- Six-role AI council (`TechnicalAnalyst`, `MarketContextAnalyst`,
  `RiskReviewer`, `SkepticalReviewer`, `TradePlanner`,
  `SynthesisReviewer`) — backed by an LLM brain. Default model is
  **`ocg/minimax-m3`** served via InferHub
  (`https://api.inferhub.dev/v1`); falls back to a deterministic
  `StubClient` when no API key is configured so the server stays
  runnable offline. Spec-defined `role_weight` and `confidence_cap`
  are always enforced on top of model output.
- The 7-stage decision engine (`app/engine/decision.py:decide`) per
  the spec: validate data → compute gates → apply vetoes → council →
  measure agreement → composite → final state. Rule decisions with 8
  unit tests.
- `POST /api/v1/analysis/run` for one-shot runs, `GET
  /api/v1/analysis/runs` for history.

### Phase 4 — done
- Background multi-symbol scanner (`POST /api/v1/scanner/run`) that
  runs the analyzer on the configured universe, persists every run,
  publishes notable candidates to Redis pub/sub, and surfaces a live
  status with progress and notable-cards.

### Phase 5 — done
- JWT + bcrypt auth with `register`, `login`, `me`, and a 401-protected
  `/api/v1/auth/me`.
- CORS lockdown via `CORS_ORIGINS`.
- `Journal` UI (and `/api/v1/journal`) — manual entries, auto-create
  from orders, close-with-exit-price, delete, summary stats.
- `Trades` UI (and `/api/v1/trades`) — paper by default; set
  `LIVE_TRADING=1` and provide `GATEIO_API_KEY/SECRET` to enable real
  signed order placement on Gate.io. Notional cap (`MAX_ORDER_NOTIONAL_USD`)
  is enforced either way.
- The trade panel shows live order status (`FILLED`/`REJECTED`/...)
  and the exchange-order id.

## Decision engine (spec at a glance)

| Step | Computes |
|---|---|
| 1. Gate score | Weighted, confidence-aware sum on [-100, 100] |
| 2. Model score | Directional role votes weighted by `role_weight × effective_confidence`, capped so skeptic/risk roles can't push confidence higher than 0.35 (but can pull it down without a cap) |
| 3. Model agreement | Weighted share of roles that agree with the composite majority |
| 4. Composite | `0.55 × gate + 0.45 × model` (configurable) |
| 5. Quorum | Must see ≥ `minimum_quorum_gate_count` gates with status |
| 6. Vetoes | Gate veto, AI hard-veto risk flag, low agreement, low data completeness |
| 7. Final state | `DATA_INVALID` → `AVOID` → `WAIT` → `LONG_CANDIDATE` → `SHORT_CANDIDATE` |

Trade plan appears only on `LONG/SHORT_CANDIDATE` and includes entry
(ATR-projected), stop (1.5×ATR opposite side), take-profit (3×ATR or
2×R:R, whichever is larger), position size, invalidation, and a
synthesis sentence.

## Data contracts

See [`docs/data-contracts.md`](docs/data-contracts.md). The full Pydantic
shapes are in `app/schemas/` and the SQLAlchemy ORM is in
`app/db/models.py`.

## Threat model

See [`docs/threat-model.md`](docs/threat-model.md). Live trading is
gated by `LIVE_TRADING` and a per-order notional cap. No exchange
private keys are read until that flag is on. The AI council in this
build is deterministic and produces no external calls; a future LLM
backend would inherit the existing hard-veto + confidence-cap
guardrails.

## Tests

```bash
cd apps/api && pytest -q     # 30 tests
cd apps/web && npm run build # type-check + production build
```

## Repo layout

```
apps/
├── api/                # FastAPI
│   ├── app/
│   │   ├── api/           # HTTP routers (auth, market_data, analysis, ...)
│   │   ├── db/            # SQLAlchemy engine, models, Redis client
│   │   ├── engine/        # Gates, council, decision engine, runner, strategy
│   │   ├── schemas/       # Pydantic request/response shapes
│   │   └── services/      # Gate.io REST + WS, execution module
│   └── tests/
└── web/                # Next.js 15 App Router
    ├── app/
    │   ├── (auth)/        # /login, /register
    │   ├── terminal/[symbol]/
    │   ├── scan/, journal/, settings/
    └── components/, lib/

packages/
├── contracts/            # JSON Schema scaffold for AnalysisRun
└── strategy-presets/     # aggressive.json, balanced.json, conservative.json

scripts/                   # bootstrap.sh, seed_demo_data.py, verify_contracts.py
docs/                      # architecture, decision-engine, data-contracts,
                           # threat-model, changelog
```
