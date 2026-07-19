# Architecture

Modular monolith, single FastAPI process with a thin Next.js frontend
and a Postgres + Redis persistence tier.

## Pipeline

```
                 ┌──────────────────────────┐
HTTP / SSE ─────►│   FastAPI (uvicorn)      │
                 │  ┌─────────────────────┐ │
                 │  │  /api/v1/auth       │ │ JWT + bcrypt
                 │  │  /api/v1/strategies  │ │ versioned config
                 │  │  /api/v1/symbols     │ │ provider + meta
                 │  │  /api/v1/market-data │ │ historical candles + SSE
                 │  │  /api/v1/analysis    │ │ orchestrates run
                 │  │  /api/v1/scanner     │ │ multi-symbol background
                 │  │  /api/v1/journal     │ │ entries + pnl
                 │  │  /api/v1/trades      │ │ orders + execution
                 │  └────────┬────────────┘ │
                 │           ▼              │
                 │  ┌─────────────────────┐ │
                 │  │  app.engine.runner  │ │ the analysis run
                 │  └────────┬────────────┘ │
                 │           │              │
                 │  ┌────────▼────────────┐ │
                 │  │ 6 deterministic     │ │
                 │  │ gates                │ │ ATR / EMA / RSI /
                 │  │                     │ │ MACD / BB / OBV /
                 │  │                     │ │ structure / order
                 │  │                     │ │ book
                 │  └────────┬────────────┘ │
                 │           ▼              │
                 │  ┌─────────────────────┐ │
                 │  │ 6-role AI council   │ │
                 │  │                     │ │ technical, market
                 │  │                     │ │ context, risk,
                 │  │                     │ │ skeptic, planner,
                 │  │                     │ │ synthesis
                 │  └────────┬────────────┘ │
                 │           ▼              │
                 │  ┌─────────────────────┐ │
                 │  │ decision engine     │ │
                 │  │ (pure function)     │ │
                 │  └────────┬────────────┘ │
                 │           ▼              │
                 │  ┌─────────────────────┐ │
                 │  │ trade plan + risk + │ │
                 │  │ synthesis            │ │
                 │  └────────┬────────────┘ │
                 │           ▼              │
                 │  ┌─────────────────────┐ │
                 │  │ SQLAlchemy ORM      │ │
                 │  │ (history, alerts,   │ │
                 │  │  orders, journal)    │ │
                 │  └────────┬────────────┘ │
                 └──────────┼──────────────┘
                            ▼
                      Postgres + Redis
```

## Modules

### `app/api`

| Router | Responsibility |
|---|---|
| `auth.py` | Register, login, `me`; JWT issuance; seeded admin on first boot. |
| `market_data.py` | `GET /candles` (historical), `GET /stream` (SSE live updates). |
| `analysis.py` | `POST /analysis/run` (one-shot), `GET /analysis/runs`, `GET /analysis/runs/{id}`. |
| `strategy.py` | `GET /strategies/presets`, `GET /strategies/active?name=…`, `POST /strategies` (creates new version), `POST /strategies/seed-defaults`. |
| `symbols.py` | `GET /symbols`, `POST /symbols/sync` (only effective for live Gate.io provider). |
| `scanner.py` | `POST /scanner/run` (background), `GET /scanner/status`, `GET /scanner/latest`. |
| `journal.py` | CRUD + summary for journal entries. |
| `trades.py` | `GET /trades/config` (live/paper), `POST /trades/orders`, `GET /trades/orders`. |

### `app/engine`

| Module | Responsibility |
|---|---|
| `gates/` | Six deterministic gates: market_regime, classical_ta, market_structure, volume_momentum, fundamental_context, risk_tradeability. Each returns a `GateEvaluation` dataclass. |
| `indicators.py` | Dependency-free implementations of EMA, RSI, MACD, ATR, BB, OBV, ADX, swing highs/lows. |
| `council.py` | Six roles. Returns `ModelOpinionData`. |
| `decision.py` | Pure `decide()` function that consumes gates + opinions + spec and returns a `DecisionResult`. Implements the 7-stage pipeline. |
| `trade_plan.py` | Builds a trade plan only when the final state is LONG/SHORT_CANDIDATE. Uses 1.5×ATR stops, 3×ATR or R:R ≥ 2 takes. |
| `strategy.py` | Pydantic models for the strategy config (gates, roles, weights, thresholds). Three presets. |
| `runner.py` | Orchestrates the full flow: data → gates → council → decision → plan → persist → alert. |

### `app/services`

| Module | Responsibility |
|---|---|
| `market_data/base.py` | `MarketDataProvider` protocol. |
| `market_data/mock_provider.py` | Deterministic fixture provider (seeded sine-wave generator). |
| `market_data/gateio_rest.py` | Live Gate.io spot REST: `/spot/candlesticks`, `/spot/order_book`, `/spot/currency_pairs`. Maps Gate.io's `BTC_USDT` pair to the terminal's `BTC/USDT`. |
| `market_data/gateio_ws.py` | Live Gate.io v4 WebSocket for candle updates. |
| `market_data/factory.py` | Env-driven selection (`MARKET_DATA_PROVIDER=mock|gateio`). |
| `execution/__init__.py` | Live/paper execution on Gate.io with HMAC-SHA512 signing. |

### `app/db`

| Module | Responsibility |
|---|---|
| `__init__.py` | SQLAlchemy engine + `get_db` FastAPI dependency; `SessionLocal` lazy factory. |
| `models.py` | All ORM tables: `User`, `StrategyConfig`, `AnalysisRun`, `GateResult`, `ModelOpinion`, `Decision`, `TradePlan`, `JournalEntry`, `SymbolMeta`, `Alert`, `Order` (with enums). |
| `redis_client.py` | Returns a real Redis client when `REDIS_URL` is set; otherwise an in-process pub/sub shim with the same `publish`/`subscribe`/`ping` surface so the rest of the app is unchanged. |

## Persistence and reproducibility

Every `AnalysisRun` row stores the `config_id` it used, so the entire
run (gates, opinions, decision, plan, alerts) is fully reproducible
from history by joining on `run_id`. Editing a strategy config bumps
its version and leaves the previous version untouched.

## Failure modes

- **DB unreachable at startup**: lifespan logs a warning and continues
  if `DATABASE_URL` starts with `sqlite`, otherwise alembic upgrade is
  best-effort.
- **Redis unreachable**: in-proc shim takes over transparently.
- **Gate.io unreachable**: REST endpoints return 502; candles served
  are from the mock provider regardless.
- **Gate crash**: the engine catches per-gate exceptions and marks the
  gate `UNAVAILABLE` so the run still completes (and may return
  `INSUFFICIENT_QUORUM → WAIT`).

## What's not yet wired

- Pluggable LLM-backed AI council (current scaffold is deterministic).
- Telegram / Discord alert dispatch (alerts are stored in DB; a
  notifier hook is a future module).
- Backtesting against historical candles.
