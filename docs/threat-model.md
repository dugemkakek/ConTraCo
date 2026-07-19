# Threat model

This document catalogues the trust boundaries, persistent secrets,
and safety controls in the system. The threat model is intentionally
conservative: every external input is treated as hostile, every
exchange interaction is gated, and every persisted secret is read
only when explicitly enabled.

## Trust boundaries

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (untrusted) ── Bearer JWT ──► FastAPI route handlers   │
└──────────────────────────────────────────────────────────────────┘
        │  ↑
        │  └─ secrets only read inside /api/v1/trades/orders when
        │     LIVE_TRADING=1; never logged; passed only to HMAC
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  Gate.io REST + WebSocket (semi-trusted)                          │
│   * public market data (no auth)                                  │
│   * private trading endpoint — signed with GATEIO_API_SECRET      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Postgres + Redis (trusted once on the docker network)            │
└──────────────────────────────────────────────────────────────────┘
```

## What the system holds

| Secret | Where loaded | Default |
|---|---|---|
| `JWT_SECRET` | `app.security.make_access_token` | dev placeholder in `app/security.py`; **must** be overridden in production via env. |
| `GATEIO_API_KEY` / `GATEIO_API_SECRET` | `app.services.execution.execute_order` | unset; trades are paper by default. |
| `DATABASE_URL` / `REDIS_URL` | env, see `app/db/` | SQLite + in-proc shim if unset. |
| `ADMIN_PASSWORD` | `app.api.auth._seed_admin_if_empty` | placeholder; default admin email is `admin@example.com`. |

## Controls

### Authentication & authorization

- JWTs are HS256-signed with `JWT_SECRET`. Tokens carry `sub` (user id),
  `iat`, `exp` (24h by default).
- Passwords are bcrypt-hashed via `passlib`. `bcrypt==3.2.2` is pinned
  because passlib 1.7.4 has known compatibility issues with bcrypt 4.x.
- Protected routers go through `Depends(get_current_user)`. The
  `/api/v1/auth/me` test verifies a missing or invalid token returns
  `401`.

### CORS

- `CORS_ORIGINS` controls allowed origins. Defaults to a single-origin
  list (`http://localhost:3000`). A wildcard (`*`) is allowed for the
  eval scaffold only and is documented in the example.

### Trade execution

- **Paper by default.** `LIVE_TRADING=0` (the default) means every
  `POST /api/v1/trades/orders` records a locally synthesized fill and
  returns `status=FILLED` with a `paper-…` exchange-order id.
- **Notional cap.** `MAX_ORDER_NOTIONAL_USD` is enforced before
  anything touches Gate.io. A 0.01 BTC @ $100k order = $1000; the
  default cap is $1000.
- **Server-side signing.** When live, the request body is HMAC-SHA512
  signed with the secret in the standard Gate.io v4 spot order format
  (PUT/POST `body` hashed, then concatenated with timestamp).
- **No order without a plan.** The UI's TradePanel only appears when
  the analysis produced `LONG_CANDIDATE` / `SHORT_CANDIDATE`. The
  HTTP API still accepts arbitrary orders but the validation rejects
  obvious junk (zero qty, negative price).

### Gate F (risk_tradeability)

Gate F is the only deterministic veto gate. Production deployments
should set:
- `GATE_F_MIN_24H_QUOTE_VOLUME` (default `100000`) — symbols with
  24h quote volume below this trigger a `VETO`.
- `GATE_F_MAX_SPREAD_BPS` (default `50`) — bid/ask spread above this
  triggers a `VETO`.
Both are read from the environment so they can be tuned without a
code change.

### AI council safety

- The current council is **deterministic** (no external LLM call).
  Every run is reproducible and runs offline.
- The hard `confidence_cap` rule from `claude reccomendation.txt` is
  enforced: `risk_reviewer` and `skeptical_reviewer` cannot push
  confidence above 0.35, but can pull it down *without* a cap so
  their bearish dissent isn't suppressed.
- `hard_veto_risk_flags` (default `["data_integrity", "liquidity_trap",
  "manipulation_suspected"]`) causes an AI flag to force `AVOID`
  immediately, regardless of direction agreement.

If a future commit introduces a real LLM-backed council, those
controls remain in place; only the role implementations change.

### Input validation

- All Pydantic request bodies validate types and ranges.
- SQLAlchemy ORM is used everywhere; no string concatenation for SQL.
- `symbol` normalization happens at the API boundary (`BTC-USDT`
  → `BTC/USDT`); the Gate.io provider further maps to the exchange's
  `BTC_USDT` pair notation internally.
- `GET /api/v1/market-data/{symbol}/candles` rejects unsupported
  symbols with `400`.

### Failure modes we *don't* try to hide

- If a single gate throws, the engine catches, marks the gate
  `UNAVAILABLE`, and lets the run continue (which usually lands at
  `WAIT/INSUFFICIENT_QUORUM` rather than a fake `LONG`).
- A 502 is returned honestly when the upstream Gate.io call fails;
  the terminal falls back to the mock provider so the UI keeps working.

## What is out of scope

- TLS termination: expected to be handled by the reverse proxy in
  front of the API.
- Multi-tenant isolation: this is a single-user-or-team tool with
  per-user scoping but no row-level security across users yet (a
  user can see only their own runs by enforcement in the API).
- Backtesting: not yet implemented.
- On-chain attestation: not part of the current build.
