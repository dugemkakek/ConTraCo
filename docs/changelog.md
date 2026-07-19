# Changelog

All notable changes to the Confluence Trading Consultant, grouped by
phase per the original spec (`claude reccomendation.txt` §12). See
[`HANDOFF.md`](../HANDOFF.md) for the operational status, known
issues, and run instructions.

---

## Phase 0 — Foundation

### Added
- `docker-compose.yml` defining web (Next.js), api (FastAPI),
  postgres:16, redis:7.
- `apps/api/Dockerfile` (Python 3.12-slim, uvicorn entrypoint) and
  `apps/web/Dockerfile` (Node 20-slim, Next dev server entrypoint).
- `Makefile` with `up`, `down`, `logs`, `api-test`, `web-test`
  shortcuts.
- `.env.example` with all service URLs and market-data, auth, and
  trade-execution knobs documented.
- FastAPI scaffold `apps/api/app/main.py` with `GET /health`.
- Pydantic `Candle` + `CandleResponse` schemas.
- Test scaffolding: `pytest.ini` with `asyncio_mode = auto`.

---

## Phase 1 — Chart Terminal

### Added
- `MockMarketDataProvider` (`apps/api/app/services/market_data/mock_provider.py`):
  seeded sine-wave + noise generator for `BTC/USDT`, `ETH/USDT`,
  `SOL/USDT` across `1m / 5m / 15m / 1h / 4h / 1d`.
- `GET /api/v1/market-data/{symbol}/candles` with per-timeframe
  freshness tolerance and `FRESH / STALE / UNKNOWN` classification.
- Next.js 15 (later upgraded to **16.2.10** for security patching)
  App Router terminal at `apps/web/app/terminal/[symbol]/page.tsx`.
- Dark `tailwind.config.ts` palette: `bg`, `panel`, `border`,
  `bullish`, `bearish`, `warning`, `neutral`, `aiAccent`, `info`.
- `CandlestickChart` component (`lightweight-charts` v4.2) with
  candle + volume + EMA 20/50/200 overlay.
- `TimeframeSelector`, `DataFreshnessBadge`, `DecisionConsole`
  (initial placeholder) components.
- `lib/api.ts` (typed REST client) and `lib/indicators.ts` (client
  EMA helper).
- Playwright config + `terminal.spec.ts` smoke.

---

## Phase 2 — Real market data + deterministic gates

### Added
- **`MarketDataProvider` Protocol** (`apps/api/app/services/market_data/base.py`)
  — pluggable interface.
- **Gate.io spot REST adapter** (`apps/api/app/services/market_data/gateio_rest.py`):
  - `GET /spot/candlesticks` with retries + exponential backoff.
  - `GET /spot/order_book` for tradeability checks.
  - `GET /spot/currency_pairs` for the scanner universe.
  - `BTC/USDT ↔ BTC_USDT` pair mapping done in the adapter.
- **Gate.io WebSocket adapter** (`gateio_ws.py`):
  - Reconnect loop with bounded jittered backoff.
  - Deduped subscriptions across SSE consumers.
  - Redis pub/sub fan-out for multi-worker; in-proc fallback for dev.
- **`scripts/factory.py`** env-driven provider selection
  (`MARKET_DATA_PROVIDER=mock|gateio`).
- **Postgres + SQLAlchemy 2 + Alembic** wiring:
  - `apps/api/app/db/__init__.py` engine + lazy `SessionLocal` factory
    + FastAPI `get_db` dependency.
  - `apps/api/app/db/models.py` with the full schema (11 tables,
    enums).
  - Alembic `alembic.ini` + `alembic/env.py` set up to read
    `$DATABASE_URL` and target `app.db.models.Base`.
  - Migration `e1583ae0b71f_initial_schema.py` generated and
    applied to a live Postgres.
- **`apps/api/app/db/redis_client.py`**:
  - Returns real `redis.asyncio` if `$REDIS_URL` reachable.
  - Otherwise an in-memory pub/sub shim with the same
    `publish/subscribe/ping/aclose` surface so the rest of the
    app stays the same.
- **Six deterministic gates** (`apps/api/app/engine/gates/`):
  - `MarketRegimeGate` — EMA 20/50/200 stack + ADX.
  - `ClassicalTAGate` — RSI + MACD histogram + Bollinger %b.
  - `MarketStructureGate` — swing highs/lows, BOS / CHoCH.
  - `VolumeMomentumGate` — vol vs MA20 + OBV slope + momentum.
  - `FundamentalContextGate` — order-book imbalance.
  - `RiskTradeabilityGate` — *the only VETO-capable gate*; checks
    24h quote volume, bid/ask spread, `is_active` flag, and the
    configurable `GATE_F_MIN_24H_QUOTE_VOLUME` /
    `GATE_F_MAX_SPREAD_BPS` env vars.
- **`apps/api/app/indicators.py`** — dependency-free Python
  implementations of EMA, SMA, RSI, MACD, ATR, ADX, BB, OBV, and
  swing-highs/lows.
- **10 unit tests** in `apps/api/tests/test_gates.py` covering
  each gate's status, score range, confidence, and veto paths.

### Changed
- `apps/api/app/api/market_data.py` now accepts `1d` and all
  Phase-2 timeframes with per-symbol fallback.
- `requirements.txt` adds `psycopg[binary]`, `redis`, `httpx`,
  `pytest`, `pytest-asyncio`.
- `apps/api/Dockerfile` runs `alembic upgrade head` on container
  start via `RUN_MIGRATIONS_ON_STARTUP=1`.

---

## Phase 3 — AI council + decision engine

### Added
- **`apps/api/app/engine/strategy.py`** — `StrategyConfigSpec`
  Pydantic model (gates, roles, weights, thresholds, hard-veto
  risk flags). Three presets loaded from
  `packages/strategy-presets/{aggressive,balanced,conservative}.json`.
  `get_active_spec()` and `save_spec()` for versioned persistence.
- **`apps/api/app/engine/council.py`** — six role classes:
  - `TechnicalAnalyst` (`directional=true`)
  - `MarketContextAnalyst` (`directional=true`)
  - `RiskReviewer` (`directional=true, capped=0.35`)
  - `SkepticalReviewer` (`directional=true, capped=0.35`)
  - `TradePlanner` (`directional=false`)
  - `SynthesisReviewer` (`directional=false`)
  - Returns `ModelOpinionData` (a separate, plain dataclass from
    the decision module's `ModelOpinionLike` Protocol to avoid a
    Python bytecode-cache footgun).
- **`apps/api/app/engine/decision.py`** — pure `decide()` function
  implementing the spec's 7-stage pipeline:
  1. Gate score (weighted, confidence-aware sum on [-100, 100])
  2. Model score (cap-aware per role)
  3. Weighted model agreement
  4. Composite (default `0.55 × gate + 0.45 × model`)
  5. Quorum + completeness (gate quorum AND data quality)
  6. Vetoes (gate veto, AI hard-veto risk flag, low agreement,
     low data completeness)
  7. Final state: `DATA_INVALID → AVOID → WAIT → LONG_CANDIDATE /
     SHORT_CANDIDATE`
- **`apps/api/app/engine/trade_plan.py`** — ATR-based entry
  (close), stop (1.5 × ATR opposite), take-profit (3 × ATR or
  R:R ≥ 2, whichever is larger), position-size cap, synthesis.
  Builds only on `LONG_CANDIDATE` / `SHORT_CANDIDATE`.
- **`apps/api/app/engine/runner.py`** — orchestrator:
  1. Resolve strategy config (saved → preset fallback).
  2. `INSERT AnalysisRun(status=RUNNING)`, commit, refresh.
  3. Run gates against the candle context.
  4. Run the council.
  5. Call `decide()`.
  6. Add `GateResult`, `ModelOpinion`, `Decision`, `TradePlan`
     rows.
  7. Emit `Alert`s for `LONG/SHORT_CANDIDATE` and `AVOID`.
  8. Commit + refresh; return the row.
- HTTP routes:
  - `POST /api/v1/strategies` (save new version, optionally
    activate).
  - `GET /api/v1/strategies/presets` and `…/active?name=…`.
  - `POST /api/v1/strategies/seed-defaults` for a fresh install.
  - `POST /api/v1/analysis/run` (returns the full `RunOut`).
  - `GET /api/v1/analysis/runs` and `…/runs/{id}`.
- **8 unit tests** in `apps/api/tests/test_decision.py` covering
  quorum, gate veto, AI veto (hard risk flag), skeptic-cap
  asymmetry, low agreement, composite-below-threshold, and the
  LONG/SHORT final-state transitions.

### Changed
- `apps/api/app/db/models.py` adds `StrategyConfig`,
  `AnalysisRun`, `GateResult`, `ModelOpinion`, `Decision`,
  `TradePlan`, `Alert`.

---

## Phase 4 — Multi-symbol scanner

### Added
- `apps/api/app/api/scanner.py`:
  - `POST /api/v1/scanner/run` starts a background scan over the
    configured universe (or caller-supplied subset) on
    `BackgroundTasks`.
  - `GET /api/v1/scanner/status` and `…/latest` for the UI.
  - Per-user `_scan_status` dict + notable candidates.
  - Redis pub/sub on `confluence:scan` for downstream notifiers.
  - 250 ms polite pacing between symbols.

---

## Phase 5 — Auth, journal, alerts, execution

### Added
- **`apps/api/app/security.py`** — JWT issuance (HS256, 24h TTL)
  + bcrypt password hashing. Wraps `python-jose` and `passlib`.
- **`apps/api/app/api/deps.py`** — `get_current_user`,
  `get_admin_user` FastAPI dependencies.
- **`apps/api/app/api/auth.py`** — `POST /auth/{register,login}`
  + `GET /auth/me`. Seeds the admin user on first boot (gated by
  `SEED_ADMIN=1`, configurable via env).
- **`apps/api/app/api/journal.py`** — journal CRUD + summary
  (open / closed / total_pnl / winners / losers). Auto-create
  journal entry from a filled order.
- **`apps/api/app/api/trades.py`**:
  - `GET /trades/config` surfaces `live_trading` flag and the
    notional cap so the UI can label its order button correctly.
  - `POST /trades/orders` supports MARKET / LIMIT, BUY / SELL,
    optional `analysis_run_id`, optional `auto_journal`.
  - `GET /trades/orders` lists order history.
- **`apps/api/app/services/execution/__init__.py`** — `OrderRequest`
  → `OrderResult`:
  - **Paper** (default, `LIVE_TRADING=0`): synthesizes a fill and
    returns `exchange_order_id = "paper-<ms>"`.
  - **Live** (`LIVE_TRADING=1` + `GATEIO_API_KEY/SECRET`): builds a
    Gate.io v4-signed `POST /spot/orders` request, with
    pre-submission notional cap (`MAX_ORDER_NOTIONAL_USD`).
- CORS lockdown via `CORS_ORIGINS` (defaults to a single origin).
- **8 integration tests** in `apps/api/tests/test_api.py` cover
  auth (register, login, 401 on missing token), analysis runs,
  strategy presets, journal close + summary, and the paper
  trade path.
- Frontend auth:
  - `apps/web/lib/auth-context.tsx` — token in `localStorage`,
     `me()` on mount, login/logout/register/refresh.
  - `apps/web/app/(auth)/{login,register}/page.tsx`.
  - `apps/web/components/terminal/TopNav.tsx` with auth-aware nav
    + logout.
  - Auth gating in every protected page.

### Changed
- `requirements.txt` adds `passlib[bcrypt]==1.7.4`, `bcrypt==3.2.2`
  (pinned for passlib compat), `python-jose[cryptography]==3.3.0`,
  `python-multipart==0.0.10`, `email-validator==2.3.0`.

---

## Frontend complete

### Added
- `lib/auth-context.tsx`, `(auth)/login`, `(auth)/register`,
  `TopNav.tsx`.
- `DecisionConsole.tsx` showing final state, gate scores, model
  agreement, veto list, per-gate status, and the council's per-role
  vote.
- `TradePanel.tsx` with paper/live toggle, order form (type,
  qty, price), `auto_journal=True` by default, status display
  (`exchange_order_id`).
- `EventSource` consumer in `terminal/[symbol]/page.tsx` — the
  latest candle is updated in place so the chart animates
  without `setData()` re-fit.
- `CandlestickChart` refactored to use `series.update()` on every
  tick after an initial `setData()`.
- `/scan`, `/journal`, `/settings` pages with full CRUD.
- Playwright e2e updated to register + login programmatically
  (the old fixture relied on the now-removed admin-only mode).

### Changed
- `apps/web/package.json`: bumped `next` → **16.2.10** (latest
  patched, fixes CVE-2025-66478), `@playwright/test` → `^1.61.0`,
  React 19.
- `apps/web/Dockerfile` unchanged but matches the upgraded
  dependencies.

---

## Phase 6 — Bug fixes & smoke-green

The previous handoff flagged two end-to-end smoke failures
(`/api/v1/symbols` returning a dict, `/strategies/active` returning
`null` on a fresh DB). This phase fixes both plus a third latent
preset-payload bug.

### Fixed
- **Duplicate `GET /api/v1/symbols` route.**
  Deleted the legacy `list_symbols` stub from
  `app/api/market_data.py`; a code comment now marks the section so
  it doesn't get re-added. `app/api/symbols.py` is now the sole
  owner of `GET /api/v1/symbols`, returning the typed
  `list[SymbolOut]` payload that the smoke and the `/scan` UI
  expect.

- **`GET /api/v1/strategies/active` returned `null` on a fresh DB.**
  `app/api/strategy.py:get_active` now delegates to
  `app.engine.strategy.get_active_spec`, which already had a
  "fall back to bundled preset" behaviour. From first boot the
  endpoint returns a usable `StrategyConfigOut` (with
  `is_active=False, version=0`) so the `/settings` page has
  something to render and the smoke's save-draft step can
  validate a real spec.

- **`load_preset()` returned an incomplete payload.**
  The `non_directional_roles` key only existed as a Pydantic
  default in `StrategyConfigSpec`; the literal `DEFAULT_CONFIG`
  dict (which `load_preset` deep-copied) didn't include it, so the
  HTTP save endpoint rejected the round-trip with
  `"Input should be a valid dictionary"`. `load_preset()` now
  round-trips through `parse_spec(DEFAULT_CONFIG)` so the returned
  dict is always fully populated by the spec model.

### Changed
- **`apps/api/smoke_e2e.py`** now calls
  `POST /api/v1/strategies/seed-defaults` between
  `GET /strategies/active` and `POST /strategies` so the version
  check (`>= 2`) succeeds on a fresh DB. A dead `next(...)` line
  that crashed with `StopIteration` was removed.

### Verified
```
$ cd apps/api && python -m pytest tests/ -v
============================= 30 passed in 4.00s ==============================

$ cd apps/api && python smoke_e2e.py
============================================================
End-to-end smoke against http://127.0.0.1:8765
============================================================
  [PASS] POST /auth/register
  [PASS] register returned user + token
  [PASS] POST /auth/login
  [PASS] GET /auth/me
  [PASS] GET /health
  [PASS] GET /symbols
  [PASS] GET /candles
  [PASS] SSE stream endpoint reachable
  [PASS] POST /analysis/run
        composite=+23.4 agreement=0.56 plan=no
  [PASS] GET /analysis/runs
  [PASS] GET /strategies/presets
  [PASS] GET /strategies/active
  [PASS] POST /strategies/seed-defaults
  [PASS] POST /strategies (save draft)
  [PASS] POST /journal
  [PASS] POST /journal/{id}/close
  [PASS] GET /journal/summary
  [PASS] GET /trades/config
  [PASS] POST /trades/orders (paper)
  [PASS] GET /trades/orders
  [PASS] POST /scanner/run
  [PASS] GET /scanner/latest
  [PASS] GET /candles (4h)
============================================================
END-TO-END SMOKE: ALL CHECKS PASSED
```

Web typecheck + production bundle:

```
$ cd apps/web && npm run build
✓ Compiled successfully in 17.9s
Route (app)
┌ ○ /          ├ ○ /login          ├ ○ /scan
├ ○ /journal  ├ ○ /register        ├ ○ /settings
├ ○ /_not-found └ ƒ /terminal/[symbol]
```

---

## Phase 7 — AI Brain (ocg/minimax-m3)

The previous handoff called out "Plug in a real LLM-backed council
that respects the existing `confidence_cap` and `hard_veto_risk_flags`
rules" as the highest-value next step. This phase delivers it.

### Added
- **`apps/api/app/services/llm/__init__.py`** — the brain provider.
  Exports a tiny `LLMClient` Protocol, two concrete clients
  (`StubClient`, `OpenAICompatClient`), and a `build_client()`
  factory.
  - `StubClient` is a deterministic echo used when no API key is
    configured; tagged `provider_used=ocg-stub`.
  - `OpenAICompatClient` POSTs to
    `{LLM_BASE_URL}/chat/completions` (default
    `https://api.inferhub.dev/v1`) with
    `response_format={"type":"json_object"}` and 2 retries with
    exponential backoff. Reads `LLM_API_KEY` or `INFERHUB_API_KEY`,
    `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`.
- **`apps/api/app/services/llm/prompts.py`** — per-role system
  prompts (technical / context / risk / skeptic / planner /
  synthesis) and `build_role_prompt(role, ctx)` that emits a
  compact user prompt containing the gate evaluations + symbol +
  timeframe + last candles. Each role adapter enforces the
  strategy spec's `role_weight` and `confidence_cap` on top of
  whatever the model returns.

### Changed
- **`apps/api/app/engine/council.py`** — replaced the six
  deterministic role classes with thin LLM-backed adapters.
  `TechnicalAnalyst`, `MarketContextAnalyst`, `RiskReviewer`, and
  `SkepticalReviewer` all call the configured client; `TradePlanner`
  and `SynthesisReviewer` still short-circuit to a WAIT/VALID
  sentinel. The module now also exposes
  `ROLE_SPEC_DEFAULTS`, `get_client()`, and `set_client()` (used by
  tests for injection).
- **`apps/api/app/engine/runner.py`** — `ModelOpinionRow.raw_output`
  now carries `provider_used` + `llm_model` so the API + UI can
  display which brain produced each opinion.
- **`apps/api/app/api/analysis.py`** — `OpinionOut` exposes
  `provider_used` + `llm_model`; `_serialize` reads them from
  `raw_output`.
- **`apps/api/app/main.py`** — `GET /health` now reports
  `llm_provider` and `llm_model` (e.g. `ocg-stub` / `ocg/minimax-m3`).
- **`.env.example`** — new section "AI Brain (LLM council)" with
  InferHub defaults (`LLM_MODEL=ocg/minimax-m3`,
  `LLM_BASE_URL=https://api.inferhub.dev/v1`), the `LLM_API_KEY` and
  `INFERHUB_API_KEY` aliases, and the timeout / retry knobs.

### Added tests
- **`apps/api/tests/test_council.py`** (4 tests):
  - `test_council_uses_stub_when_no_api_key` — every opinion
    tagged `ocg-stub` with `model=ocg/minimax-m3` when no key is
    set.
  - `test_council_enforces_role_weights_and_caps` — a client
    returning `confidence=0.99` is clamped to the spec caps
    (`risk_reviewer` + `skeptical_reviewer` stay ≤ 0.35).
  - `test_council_survives_garbage_llm_response` — a client that
    raises `LLMError` leaves 4 directional roles as
    `MISSING` (the decision engine treats them as abstentions)
    while `trade_planner` + `synthesis_reviewer` still complete.
  - `test_set_client_round_trip` — `set_client()` injection works.

### Verified
```
$ cd apps/api && python -m pytest tests/ -v
============================= 34 passed in 4.00s ==============================
tests/test_council.py::test_council_uses_stub_when_no_api_key PASSED
tests/test_council.py::test_council_enforces_role_weights_and_caps PASSED
tests/test_council.py::test_council_survives_garbage_llm_response PASSED
tests/test_council.py::test_set_client_round_trip PASSED

$ cd apps/api && python smoke_e2e.py
END-TO-END SMOKE: ALL CHECKS PASSED        # 23 / 23

$ cd apps/web && npm run build
✓ Compiled successfully in 3.8s
Route (app)
┌ ○ /          ├ ○ /login          ├ ○ /scan
├ ○ /journal  ├ ○ /register        ├ ○ /settings
├ ○ /_not-found └ ƒ /terminal/[symbol]
```

Live end-to-end (api :8000 + web :3000):

```
$ curl -s http://127.0.0.1:8000/health
{"status":"ok","redis_mode":"inproc","market_data_provider":"mock",
 "llm_provider":"ocg-stub","llm_model":"ocg/minimax-m3"}

$ curl -s http://127.0.0.1:3000/login
<full login page rendered>

$ curl -s -X POST http://127.0.0.1:8000/api/v1/auth/register \
       -H 'Content-Type: application/json' \
       -d '{"email":"…","password":"VeryStrong1!"}'
# … then POST /api/v1/analysis/run returns
final_state=LONG_CANDIDATE, composite=+36.7, agreement=1.00,
every opinion tagged provider_used=ocg-stub, llm_model=ocg/minimax-m3
```

### How to enable a real brain

```
echo 'LLM_API_KEY=sk-airo-...' >> .env       # inferhub key
# restart uvicorn
curl -s http://127.0.0.1:8000/health
# llm_provider flips from "ocg-stub" to "ocg"
```

No code changes required — the swap is purely env-driven.

---

## Tooling & docs

### Added
- `docs/architecture.md` — full module breakdown + persistence
  notes + failure modes.
- `docs/decision-engine.md` — the spec + 7-step pipeline in one
  place, with the cap-asymmetry rationale.
- `docs/data-contracts.md` — JSON shapes for the public API.
- `docs/threat-model.md` — trust boundaries, secrets, controls,
  what's *not* in scope.
- `docs/changelog.md` — this file.
- `README.md` — quick start, feature list, repo layout, tests.
- `HANDOFF.md` — operational state, run instructions, known
  issues, what the next agent should do.
- `apps/api/smoke_e2e.py` — runnable end-to-end smoke (urllib
  only, no shell).

### Known issues (from HANDOFF.md §6)
1. ~~Two `/api/v1/symbols` endpoints registered~~ — **FIXED** in
   Phase 6.
2. ~~`GET /strategies/active` returned `null` on a fresh DB~~ —
   **FIXED** in Phase 6.
3. ~~`load_preset()` returned an incomplete payload~~ — **FIXED**
   in Phase 6.
4. `MARKET_DATA_PROVIDER=gateio` opens a WS at startup; offline
   sandbox will spam reconnect logs (cosmetic).
5. SQLite startup requires `RUN_MIGRATIONS_ON_STARTUP=1` so
   `Base.metadata.create_all` runs (Postgres uses Alembic).
6. Council/decision dataclasses are **deliberately separate** to
   avoid a Python bytecode-cache staleness footgun; clearing
   `__pycache__` after engine edits is mandatory (the conftest
   does this automatically).
7. bcrypt is pinned to 3.2.2 (passlib 1.7.4 + bcrypt 4.x is broken).
8. The live-trading branch of `services/execution/__init__.py`
   is type-checked but was never run against real Gate.io in this
   sandbox. Always start with a $1 market order on a test
   account.
9. **No real LLM key was used in Phase 7.** The default brain is
   `ocg-stub` because no `LLM_API_KEY` was available. Drop an
   InferHub key (`sk-airo-…`) into `.env` and restart to flip to
   the live `ocg/minimax-m3` model — see Phase 7 changelog above.

---

## Verified evidence

```bash
$ cd apps/api && python -m pytest tests/
============================= 34 passed in 4.00s ==============================

$ cd apps/web && npm run build
Route (app)
┌ ○ /          ├ ○ /login          ├ ○ /scan
├ ○ /register  ├ ○ /settings       ├ ○ /journal
├ ○ /_not-found └ ƒ /terminal/[symbol]
✓ Compiled successfully in 17.9s
```

`apps/api/smoke_e2e.py` (live uvicorn on :8765): **23 / 23** checks
PASS. The previously-failing `/symbols`, `/strategies/active`, and
`/strategies (save draft)` checks are now green. See
`HANDOFF.md` §5 for the run instructions.
