# Migration Gap Analysis: NewConfluenceTrader Spec → confluence-trading-consultant

> Generated 2026-07-22 by Aoi. Source spec: F:\Programs\NewConfluenceTrader (14 docs).
> Target: F:\Programs\confluence-trading-consultant (existing codebase).

## Executive Summary

The old project has a working skeleton (FastAPI + Next.js, 10 deterministic gates, 4 LLM council roles, basic decision engine) but is **missing ~70% of the spec's feature surface** and the **core confluence math doesn't match spec 04**. The LLM council is doing work that should be deterministic. The UI is a basic dashboard, not the Neo-Bloomberg terminal.

---

## 1. CONFLUENCE ENGINE (spec 04) — CRITICAL MISMATCH

### Old (decision.py)
```
composite = gate_score × 0.6 + model_score × 0.4
final_state: LONG_CANDIDATE if composite ≥ 55, SHORT if ≤ -55, else WAIT
```

### New (spec 04 — locked)
```
C_total = (Σ(weight_i × direction_i × confidence_i) / Σ weight_i) × 100
Score bands: ≥75 Strong (green), 50-74 Moderate (yellow), <50 Divergent (red)
Regime-weighted: weight_i_effective = weight_i × regime_multiplier(gate_i, regime)
MTC bonus: +10-15% if HTF/MTF/LTF align, capped at 100
Invalidation framing: primary scenario + alternative + invalidation trigger (mandatory)
Kelly: f* = (bp - q) / b, half-Kelly default, N≥30 sample gate
```

**Gap:** Formula wrong. Score bands wrong. No regime weighting. No MTC bonus. No scenario framing. No Kelly.

---

## 2. AI COUNCIL (spec 03) — ARCHITECTURE INVERSION

### Old
- 4 LLM roles (technical_analyst, market_context, risk_reviewer, skeptical_reviewer) each call LLM for direction+confidence
- LLM **invents** the direction/confidence numbers
- 2 non-directional roles (trade_planner, synthesis_reviewer) are stubs

### New (spec 03 — locked)
- 7+1 deterministic gate agents compute direction/confidence from math
- LLM only generates reasoning text from already-computed values
- CRO aggregates all gate verdicts into weighted confluence score
- Debate protocol: bull/bear/neutral grouping, low-conviction flagging
- Regime detection adjusts gate weights dynamically

**Gap:** Architecture inverted. LLM should narrate, not decide. Missing: Funding Rate gate, Liquidity Heatmap gate, Pattern Recognition gate, Orderbook microstructure gate, CRO agent, debate protocol, regime-aware weighting.

---

## 3. GATES — MISSING 4 OF 8

### Old (10 gates, all deterministic)
classical_ta, fibonacci_levels, fundamental_context, ichimoku_cloud,
market_regime, market_structure, market_structure_smc, on_chain_flow,
risk_tradeability, volume_momentum

### New (spec 03 — 7+1 gates)
| Gate | Old? | Status |
|---|---|---|
| 1. Fundamental | ✅ fundamental_context | Exists, needs verdict contract |
| 2. Technical Analysis | ✅ classical_ta + ichimoku + fibonacci | Exists, needs consolidation |
| 3. Price Action | ✅ market_structure + market_structure_smc | Exists, needs consolidation |
| 4. Orderbook | ❌ | **MISSING** — microstructure read |
| 5. Funding Rate | ❌ | **MISSING** — derivatives positioning |
| 6. Liquidity Heatmap | ❌ | **MISSING** — liquidation magnets |
| 7. Pattern Recognition | ❌ | **MISSING** — algorithmic detection |
| 8. On-Chain (stub) | ✅ on_chain_flow | Exists as stub |
| CRO | ❌ | **MISSING** — consensus + debate |

**Gap:** 4 gates missing. Existing gates don't follow the verdict contract (direction/-1/0/1, confidence 0-1, weight, reasoning, evidence, timestamp, gate_version).

---

## 4. DATA PIPELINES (spec 05) — NO CANONICAL SNAPSHOT

### Old
- `GateioRestProvider` fetches OHLCV + orderbook directly
- No normalization layer, no cache TTL, no rate-limit budget
- No `MarketSnapshot` canonical schema

### New (spec 05 + 14 Files.md)
- Canonical `MarketSnapshot`: timestamp, exchange, symbol, OHLCV, indicators, orderbook, funding, OI, Fear&Greed, BTC dominance, news, patterns, liquidity zones, API freshness
- Pipeline: Fetch → Normalize → Cache (Redis, per-type TTL) → Serve → Persist (Timescale)
- Rate-limit budget tracker per provider
- Failover: insufficient data, not crash. Stale-data flag.

**Gap:** No snapshot schema. No pipeline. No cache TTL. No rate-limit management. No failover.

---

## 5. UI/UX (spec 06+07) — BASIC DASHBOARD vs NEO-BLOOMBERG

### Old
- Basic Next.js + Tailwind dashboard
- No design system, no component library
- No multi-chart, no gate matrix, no confluence gauge, no debate chamber

### New (spec 06+07 — locked)
- Neo-Bloomberg: `#0B0E14` base, `#151924` panels, JetBrains Mono numbers, Inter labels
- Cyan `#00F0FF` active, emerald `#10B981` bull, rose `#F43F5E` bear, amber caution
- 7 screens: Mission Control, Chart Lab, Debate Chamber, Strategy Sandbox, Journal, Arbitrage, Settings
- Components: Confluence Gauge, Gate Matrix (7+1 LEDs), Debate Chamber split, Agent Leaderboard, Orderbook Depth, Arbitrage Matrix, News Feed, Backtest Panel, Journal Table
- Cmd+K palette, keyboard shortcuts, resizable grid, layout presets, zero-clutter mode
- Colorblind-safe theme variant required

**Gap:** Everything. The old UI is a prototype. The spec is a trading terminal.

---

## 6. SCHEDULING (spec 02 FR-5/FR-6) — MISSING

- Auto-scan on logon
- Killzone triggers (Asia/London/NY opens, configurable)
- Headless scan → journal + alert

**Gap:** No scheduler exists.

---

## 7. BACKTESTING (spec 08) — BASIC vs FULL

### Old
- `backtest_runner.py` exists (~basic)

### New
- Reuse exact live gate logic (single source of truth)
- Walk-forward: in-sample tune → out-of-sample validate
- No lookahead bias (critical constraint)
- Output: net return, WR, max DD, Sharpe, profit factor, equity curve vs B&H
- Per-gate accuracy breakdown → leaderboard
- Skip LLM reasoning in backtest (deterministic only)

**Gap:** Walk-forward missing. No-lookahead guarantee unverified. Equity curve missing. Per-gate attribution missing.

---

## 8. RISK ENGINE (spec 09) — PARTIAL

### Old
- `position_sizer.py`, `drawdown_guard.py` exist

### New
- Kelly Criterion (half-Kelly default, N≥30 gate)
- Risk-of-Ruin calculation
- Drawdown analyzer (council vs idealized overlay)
- Portfolio exposure (correlation-adjusted, manual position logging)

**Gap:** Kelly missing. Risk-of-ruin missing. Portfolio exposure missing.

---

## 9. JOURNAL (spec 07 Screen 5) — PARTIAL

### Old
- `journal.py` API exists

### New
- Auto-log every recommendation (accepted/rejected/ignored)
- Manual annotation per entry
- P&L attribution by agent/gate over time
- Export PDF/CSV
- Agent performance leaderboard (7/30/90 day rolling accuracy)

**Gap:** Annotation missing. P&L attribution missing. Leaderboard missing. Export missing.

---

## 10. DATABASE (spec 10) — PARTIAL

### Old
- SQLite via SQLAlchemy + Alembic

### New
- PostgreSQL + TimescaleDB (time-series)
- Redis (cache only)
- Tables: recommendations, gate_verdicts, market_snapshots (hypertable), agent_performance, watchlist, settings, backtest_runs, alerts_log
- gate_version on every recommendation + backtest run

**Gap:** No Timescale. No market_snapshots hypertable. No agent_performance. No gate_version tracking.

---

## Implementation Priority (per spec 13 roadmap)

| Stage | What | Impact |
|---|---|---|
| **A** | Fix confluence formula + score bands + regime weights | Core logic correctness |
| **B** | Add 4 missing gates + CRO + debate protocol | Council completeness |
| **C** | MarketSnapshot + data pipeline + cache | Data foundation |
| **D** | Neo-Bloomberg UI: Mission Control + Gate Matrix + Gauge + Debate | User-facing value |
| **E** | Scheduling + alerts | Automation |
| **F** | Backtesting + risk engine + journal + leaderboard | Analytics depth |
| **G** | Arbitrage screen + Settings + Cmd+K + polish | Completeness |

---

## What We Keep From Old Project

- FastAPI app structure (`apps/api/app/`)
- SQLAlchemy models + Alembic migrations (extend, don't rewrite)
- Gate infrastructure (`GateContext`, `GateEvaluation`, `ALL_GATES` registry)
- LLM client (`app/services/llm/`) — repurpose for reasoning-text-only
- WebSocket hub (`app/services/realtime/`)
- Next.js app shell (`apps/web/`) — restyle, don't rebuild
- Test suite (77 tests) — extend

## What We Change

- `decision.py` → rewrite to spec 04 formula
- `council.py` → LLM narrates only, deterministic gates decide
- `runner.py` → add MarketSnapshot, parallel gate execution, CRO step
- UI → Neo-Bloomberg design system overlay
- DB → add Timescale tables, gate_version, agent_performance
