# Phase 9.5 Safe Top Ticker Design

**Date:** 2026-07-20  
**Status:** Approved for implementation  
**Scope:** Repair the Neo-Bloomberg dashboard top ticker with verified free/public data, source/freshness metadata, and fail-closed presentation.

## Context

The uncommitted Phase 9.5 dashboard redesign introduced `TopTicker`, but the component currently:

- requests `/api/v1/overview`, while the existing backend route is `/api/v1/market-overview`;
- hard-codes BTC dominance, Fear & Greed, and gas values;
- labels the strip `LIVE` even when those values are fabricated.

This violates the approved product constraint that runtime market data must come from real/public APIs and that unavailable critical data must fail closed rather than silently falling back to mock or synthetic values.

## Verified Free/Public Source Boundary

Research verified one production-eligible data path for this implementation:

| Metric | Source | Endpoint | Response field | Implementation decision |
|---|---|---|---|---|
| BTC dominance | CoinGecko public API | `GET https://api.coingecko.com/api/v3/global` | `data.market_cap_percentage.btc` | Fetch best-effort, cache for 10 minutes locally, identify as `CoinGecko`, and display only after numeric validation. |
| Fear & Greed | None verified for free production use | — | — | Render `N/A · SOURCE UNVERIFIED`; make no HTTP request. |
| Ethereum gas | None verified for free production use | — | — | Render `N/A · SOURCE UNVERIFIED`; make no HTTP request. |

The CoinGecko public-host request returned a numeric BTC-dominance field without a key during verification on 2026-07-20. The research did **not** establish enforceable no-key rate limits, commercial terms, attribution terms, or a stable SLA. The adapter must therefore be treated as best-effort public enrichment, must use local caching to minimize calls, and must fail closed on every transport, HTTP, parse, or validation error.

Do not add Alternative.me, Etherscan, an anonymous Ethereum RPC, or a paid API key to this implementation. Their production-use terms and/or reliability requirements were not verified sufficiently.

Research references:

- [CoinGecko global crypto data reference](https://docs.coingecko.com/reference/crypto-global)
- [CoinGecko Demo global crypto data reference](https://docs.coingecko.com/demo/reference/crypto-global)
- [CoinGecko authentication reference](https://docs.coingecko.com/reference/authentication)
- [CoinGecko rate-limit/common-errors reference](https://docs.coingecko.com/docs/common-errors-rate-limit)

## Architecture

Add a focused backend macro-enrichment service. It owns CoinGecko request construction, a process-local TTL cache, numeric validation, per-metric timestamps, and safe unavailable results. The existing market overview route calls this service once per response and includes a backward-compatible `macro` object in its JSON response.

The frontend consumes the existing `getMarketOverview()` helper, now typed with `macro`, and never makes ad-hoc macro API requests. `TopTicker` derives display status from the market provider, the overview timestamp, and each metric’s availability/freshness.

## API Contract

`GET /api/v1/market-overview` retains all existing fields and adds:

```json
{
  "macro": {
    "btc_dominance": {
      "value": 57.42,
      "unit": "percent",
      "source": "CoinGecko",
      "source_url": "https://api.coingecko.com/api/v3/global",
      "retrieved_at": "2026-07-20T16:00:00+00:00",
      "freshness": "FRESH",
      "error": null
    },
    "fear_and_greed": {
      "value": null,
      "unit": "index",
      "source": null,
      "source_url": null,
      "retrieved_at": null,
      "freshness": "UNAVAILABLE",
      "error": "source_unverified"
    },
    "ethereum_gas": {
      "value": null,
      "unit": "gwei",
      "source": null,
      "source_url": null,
      "retrieved_at": null,
      "freshness": "UNAVAILABLE",
      "error": "source_unverified"
    }
  }
}
```

### Macro metric rules

- `value` is `float | null`; no substitute or stale numeric value may be returned after cache expiry or source failure.
- `freshness` is exactly `FRESH`, `STALE`, or `UNAVAILABLE`.
- A locally cached CoinGecko response is `FRESH` for less than 10 minutes since `retrieved_at`; it becomes `STALE` at or after 10 minutes and its numeric value must become `null`.
- `source`, `source_url`, `retrieved_at`, and `error` make the displayed provenance inspectable.
- Fear & Greed and Ethereum gas are explicit sentinel records, not absent JSON keys. They do not cause outbound requests.

## UI Design

The ticker remains a compact single-row terminal strip using the existing Neo-Bloomberg visual language:

- deep panel background and hairline separator;
- monospaced numeric values;
- terse uppercase status language;
- status conveyed by both visible text and an indicator, never color alone.

### Fields

| Field | Display rule |
|---|---|
| BTC | Show formatted `last` from `BTC/USDT` only when the configured market provider is not `mock`; otherwise `—`. |
| BTC 24h | Show signed `change_24h_pct` only with a non-mock BTC price. |
| BTC.D | Show `macro.btc_dominance.value` formatted to one decimal and `%` only when `freshness=FRESH`; otherwise `N/A`. |
| Fear & Greed | Show `N/A`; title text is `Public data source is not verified for production use`. |
| Gas | Show `N/A`; title text is `Public data source is not verified for production use`. |

BTC dominance carries `title="Source: CoinGecko"`. Unavailable enrichment carries a concise accessible explanation. No metric uses a default numeric value.

## Status Model

The status is derived from query state, `as_of`, configured market provider, BTC availability, and macro metric freshness.

| Status | Condition |
|---|---|
| `OFFLINE` | The market-overview query has failed, or no response is available after failure. |
| `STALE` | A response exists, but `as_of` is invalid or 90 seconds old or older. |
| `DEGRADED` | The response is fresh, but the market provider is `mock`, BTC price is unavailable, any metric is stale/unavailable, or a macro metric reports an error. Because Fear & Greed and gas are intentionally unverified, normal Phase 9.5 operation is `DEGRADED`, never `LIVE`. |
| `LIVE` | Reserved for a future state in which the overview and every displayed metric has a configured, successful, fresh, non-mock source. This implementation must not claim `LIVE`. |

A failed refetch may leave a previously rendered value visible through React Query, but status must immediately show `OFFLINE` and never imply the value is current.

## Error and Freshness Handling

- The CoinGecko adapter uses `httpx.AsyncClient` with a 10-second timeout and the application user agent.
- It caches only validated numeric responses in process memory for 10 minutes.
- It does not use a stale value after expiry, and it does not retry in the request path.
- All provider failure classes—including non-2xx HTTP, timeout, transport error, invalid JSON, missing field, non-numeric field, or out-of-range percentage—return an unavailable metric record with a stable error code and no numeric value.
- The existing overview endpoint remains successful when macro enrichment is unavailable; this is a partial-data dashboard view, not a trade approval endpoint. The frontend exposes the degraded condition visibly.
- A configured `MARKET_DATA_PROVIDER=mock` is never presented as live market data. This preserves test/development support while preventing production-style claims in the UI.

## Accessibility

- Status always includes visible text.
- Positive and negative BTC change use both a sign and color.
- Unavailable values use readable `N/A` text, not blank space.
- Tooltips/titles identify source or unavailable reason.

## Testing

Implementation follows TDD.

### Backend tests

1. A validated CoinGecko payload yields `FRESH`, a numeric BTC dominance value, CoinGecko provenance, and a retrieval timestamp.
2. A second read before TTL expiry uses the cached validated record and makes no second HTTP request.
3. Each malformed/failed response category yields `UNAVAILABLE`, `value=null`, and a stable error code; no synthetic or stale number survives.
4. The overview endpoint exposes all three macro keys, preserves the current overview fields, and leaves unverified metrics as explicit `source_unverified` records.

Unit tests inject an `httpx.MockTransport` into the macro service; these are parsing/cache tests, not provider-live fixtures. Add a separately marked, opt-in live contract smoke that calls CoinGecko only when `RUN_LIVE_PROVIDER_TESTS=1`; it validates only the documented field shape and must not run by default in CI.

### Frontend checks

1. `TopTicker` uses `getMarketOverview()` and never `/api/v1/overview`.
2. Non-mock fresh BTC and fresh BTC dominance render supplied values.
3. A mock-backed overview renders no synthetic BTC price and does not display `LIVE`.
4. Unverified Fear & Greed and gas render `N/A` with source-unverified titles.
5. Query failure renders `OFFLINE`; invalid/old `as_of` renders `STALE`.

Use the existing Playwright setup for browser coverage; do not add a new frontend unit-test framework for this task.

### Regression verification

- `apps/api/venv/Scripts/python.exe -m pytest apps/api/tests -q`
- `npm --prefix apps/web run lint`
- `npm --prefix apps/web run build`
- Existing dashboard Playwright coverage plus the focused ticker assertions when the local API/web services are running.

## Non-Goals

- Adding paid API subscriptions or storing any API key.
- Integrating Fear & Greed or Ethereum gas before their sources are independently verified for production use.
- Changing the existing market-data provider abstraction or trading approval logic.
- Redesigning the dashboard grid, chart, council, debate chamber, or order-book panel.
- Treating a mock provider as real production data.

## Definition of Done

- The ticker calls the existing market-overview API client.
- BTC dominance comes only from a validated, fresh CoinGecko global response.
- Fear & Greed and gas are truthful `N/A` records with explicit source-unverified metadata.
- No hard-coded market/enrichment numbers remain.
- No stale, mock, or failed data is labeled `LIVE`.
- Backend tests, web TypeScript validation, and production build pass.
- The repair does not disturb unrelated uncommitted V2 work.
