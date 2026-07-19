# Data contracts

JSON shapes for the public API. The Pydantic definitions are the
source of truth (see `apps/api/app/schemas/` and
`apps/api/app/api/`).

## `GET /api/v1/market-data/{symbol}/candles`

`symbol` is `BTC-USDT` or `BTC/USDT`; either format is accepted.

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "candles": [
    {
      "timestamp": "2026-07-15T06:00:00Z",
      "open": 65000.00, "high": 65100.00, "low": 64900.00,
      "close": 65050.00, "volume": 123.45
    }
  ],
  "latest_candle_timestamp": "2026-07-15T06:00:00Z",
  "data_freshness": "FRESH"   // FRESH | STALE | UNKNOWN
}
```

## `GET /api/v1/market-data/{symbol}/stream`

Server-Sent Events. Each `data:` payload is a JSON candle update:

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "timestamp": "2026-07-15T07:00:00Z",
  "open": 65050.00, "high": 65120.00, "low": 65040.00,
  "close": 65100.00, "volume": 200.0,
  "is_closed": true
}
```

When `is_closed` is `true`, the bar has rolled over and a new entry is
appended to the history. Otherwise the client should update the most
recent bar in place so the chart animates continuously.

## `POST /api/v1/analysis/run`

Request:
```json
{ "symbol": "BTC/USDT", "timeframe": "1h", "strategy": "balanced" }
```

Response (full `RunOut`):
```json
{
  "id": 42,
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "status": "COMPLETED",
  "final_state": "LONG_CANDIDATE",
  "config_id": 1,
  "started_at": "...",
  "completed_at": "...",
  "note": null,
  "gates": [
    {
      "name": "market_regime",
      "status": "PASS",
      "score": 80.0, "weight": 0.18, "confidence": 0.7,
      "reason": "uptrend …",
      "evidence": { "adx": 31.5, "...": "..." }
    }
  ],
  "opinions": [
    {
      "role": "technical_analyst",
      "status": "VALID", "direction": "LONG",
      "confidence": 0.8, "role_weight": 0.34, "confidence_cap": 1.0,
      "reason": "...", "risk_flags": [], "evidence_ids": ["classical_ta", "..."]
    }
  ],
  "decision": {
    "final_state": "LONG_CANDIDATE",
    "gate_score": 60.4, "model_score": 70.1,
    "composite_score": 64.8, "model_agreement": 0.85,
    "data_completeness": 1.0, "model_completeness": 1.0,
    "vetoes": [], "veto_sources": [],
    "reason": "long: composite 64.8 ≥ 55"
  },
  "trade_plan": {
    "direction": "LONG",
    "entry_price": 65050.0, "stop_price": 64825.0,
    "take_profit": 65750.0, "risk_reward": 2.33,
    "position_size_pct": 0.75,
    "invalidation": "Close below 64825.00 on the 1h timeframe",
    "risk_review": "Stop is 1.5×ATR …",
    "synthesis": "LONG candidate on BTC/USDT 1h. …"
  }
}
```

## `POST /api/v1/strategies`

Save a new strategy config version.

Request:
```json
{ "name": "balanced", "payload": { /* StrategyConfigSpec */ }, "activate": true }
```

Response: the saved `StrategyConfigOut` including the bumped `version`
and `is_active` flag.

## `POST /api/v1/trades/orders`

Request:
```json
{
  "symbol": "BTC/USDT",
  "side": "BUY",
  "order_type": "LIMIT",
  "qty": 0.01,
  "price": 60000,
  "analysis_run_id": 42,
  "auto_journal": true
}
```

Response: the `OrderOut` with `status ∈ {PENDING, SUBMITTED, FILLED, PARTIALLY_FILLED, CANCELED, REJECTED}` and the exchange-order id.

A `502` or rejection is returned if `LIVE_TRADING=1` and credentials
are missing, or if the order notional exceeds
`MAX_ORDER_NOTIONAL_USD`.
