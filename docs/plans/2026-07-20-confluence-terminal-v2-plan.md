# Confluence Trading Terminal V2 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task, or execute directly. 

**Goal:** Transform the existing dashboard into an institutional-grade decision intelligence engine by adding Agent Debate, Multi-Timeframe Confluence, Kelly Criterion Sizing, Arbitrage Scanning, and advanced Orderbook UI.

**Architecture:** Python/FastAPI backend extending the LangGraph/State-Machine council. React/Next.js frontend using Zustand and TradingView Lightweight charts.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js, Tailwind, React Query.

---

## PHASE 9.5: UI/UX Terminal Layout Redesign ("Neo-Bloomberg")

**Why:** The current dashboard (`app/dashboard/page.tsx`) needs to transition from a simple layout into a high-density, strict-hierarchy terminal grid.
**Impact:** ★★★★★  **Effort:** High  **Dependencies:** None
**Priority:** 0th (Do this first)

### Specification
Redesign `apps/web/app/dashboard/page.tsx` using `react-resizable-panels` to match the "Neo-Bloomberg" 4-panel grid layout. Implement strict typography and color semantics.

**Requirements:**
1. **Add Dependency:** Install `react-resizable-panels`.
2. **Color & Typography:** Enforce `#0B0E14` (Deep Slate) backgrounds, `#151924` (Panel Containers), and `JetBrains Mono` for all numbers.
3. **4-Panel Layout (Grid):**
   - **Top Bar:** Macro Ticker (BTC Dom, Fear & Greed, Gas).
   - **Panel 1 (Main/Left-Top):** TradingView Chart spanning 70% width.
   - **Panel 2 (Right-Top):** The Agent Council (Gate Matrix + Confluence Gauge + Action Card).
   - **Panel 3 (Left-Bottom):** Multi-Exchange Arbitrage & Orderbooks (from Phase 13/15).
   - **Panel 4 (Right-Bottom):** Debate Chamber & RSS News Feed (from Phase 11).
4. **Update `page.tsx`:** Refactor the flex-based layout into `PanelGroup` from `react-resizable-panels` with horizontal and vertical splits matching the above layout.

---

## PHASE 10: Multi-Timeframe Confluence (MTC) Engine

**Why:** A valid 5m setup is dangerous if the 4H trend is against it. The council must evaluate HTF/MTF/LTF alignment.
**Impact:** ★★★★★  **Effort:** High  **Dependencies:** None
**Priority:** 1st

### Specification
The engine needs to run the 7 confirmation gates across 3 timeframes simultaneously (e.g., 4H, 1H, 15m) and combine them into a single MTC score.

**Requirements:**
1. Modify `app.engine.runner.run_analysis` to accept `timeframes: list[str]` instead of a single timeframe.
2. Fetch candles and run the `ALL_GATES` loop for each timeframe independently.
3. Modify `CouncilContext` to hold a nested dict of gates by timeframe.
4. Update LLM Prompts (`app.services.llm.prompts.py`) to serialize gates by timeframe so the AI sees the HTF/LTF alignment.
5. Create `app/api/mtf.py` for new multi-timeframe endpoints if needed.

---

## PHASE 11: Agent Debate Chamber UI

**Why:** Users need to see the tension between agents (e.g., TA is bullish but Risk is vetoing).
**Impact:** ★★★★☆  **Effort:** Medium  **Dependencies:** None
**Priority:** 2nd

### Specification
Create a split-panel chat interface showing the "Bull Case" vs "Bear Case" based on the stored `ModelOpinion` reason strings and risk flags.

**Requirements:**
1. Create `apps/web/components/decision/DebateChamber.tsx`.
2. Group opinions from `run.opinions` into `BULLISH`, `BEARISH`, and `NEUTRAL/VETO`.
3. Render them as a chat-log format with timestamps and agent avatars/icons.
4. Add the `DebateChamber` component to the `AnalysisTabs.tsx` or a dedicated panel in the Dashboard grid.

---

## PHASE 12: Dynamic Position Sizing (Kelly Criterion)

**Why:** Optimal bet sizing maximizes compounding and prevents ruin.
**Impact:** ★★★★★  **Effort:** Medium  **Dependencies:** Backtest Engine
**Priority:** 3rd

### Specification
Enhance the existing `app/engine/risk/position_sizer.py` and `TradePlan` builder to use the Kelly Criterion based on the user's historical win rate and the setup's R:R.

**Requirements:**
1. Update `app.engine.risk.position_sizer.calculate_position_size`. 
2. Formula: `f* = (bp - q) / b` (b = Risk:Reward ratio, p = Win Rate, q = 1 - p).
3. Query the user's historical win rate from `app.services.analytics.trade_analytics` (or use a default 0.55 if not enough trades).
4. Update `TradePlanDetail.tsx` in the frontend to display the "Kelly Suggestion" vs the "Conservative Suggestion".

---

## PHASE 13: Delta-Neutral Yield & Arbitrage Scanner

**Why:** Cash-and-carry funding arbitrage is a core institutional strategy.
**Impact:** ★★★☆☆  **Effort:** High  **Dependencies:** Multi-venue registry
**Priority:** 4th

### Specification
Build a background scanner that compares perp funding rates and spot prices across venues (Binance, Gate.io, Bybit) to find risk-free yield.

**Requirements:**
1. Create `app/db/models.py` -> `YieldOpportunity` table.
2. Create `app/services/arbitrage/scanner.py` that queries funding rates and spot/perp spreads across `_VENUE_REGISTRY`.
3. Create `app/api/arbitrage.py` -> `GET /api/v1/arbitrage/yield`.
4. Create frontend `apps/web/components/arbitrage/FundingSniper.tsx` to display a data table of opportunities (Asset, Long Venue, Short Venue, Net APY).

---

## PHASE 14: On-Chain & Whale Tracking Gate

**Why:** Smart money movements precede price action.
**Impact:** ★★★★☆  **Effort:** High  **Dependencies:** External API (e.g., Etherscan/Dune mock)
**Priority:** 5th

### Specification
Add an 8th confirmation gate to the engine that evaluates net exchange flows and whale wallet movements.

**Requirements:**
1. Create `app/engine/gates/on_chain_flow.py` implementing `BaseGate`.
2. Add to `ALL_GATES` in `app/engine/gates/__init__.py`.
3. Create a mock or real data fetcher in `app/services/fundamentals/onchain.py` (fetching Net Exchange Flow).
4. Update the DB `GateResult` to store this new gate.

---

## PHASE 15: Liquidity Heatmaps & Orderbook Depth UI

**Why:** Traders need to see where stop-losses and liquidations sit directly on the chart.
**Impact:** ★★★★★  **Effort:** Very High  **Dependencies:** TradingView Widget
**Priority:** 6th

### Specification
Overlay orderbook depth and liquidation clusters onto the TradingView chart or in an adjacent high-density panel.

**Requirements:**
1. Update `apps/web/components/terminal/OrderBook.tsx` to include an imbalance meter (bids vs asks ratio).
2. Create `apps/api/app/api/liquidity.py` to serve mock/real liquidation cluster price levels.
3. In `TradingViewChart.tsx`, use the Lightweight Charts API (or Advanced Chart drawing tools) to plot horizontal lines or shaded regions representing liquidity pools.

---

### Implementation Prompt for Coding Agent

```text
You are implementing Phase [N] of the Confluence Trading Terminal V2.

EXISTING PROJECT CONTEXT:
- Stack: FastAPI (Backend), Next.js 14 / Tailwind (Frontend)
- Repo layout: apps/api/ (backend), apps/web/ (frontend)
- Review HANDOFF.md for current architecture state.

PHASE [N] SPECIFICATION:
[Paste the specific phase block from above]

REQUIREMENTS:
1. Create all new backend files and services.
2. Modify existing files carefully using standard python/react practices.
3. Ensure backend changes are exposed via FastAPI routers and registered in `main.py`.
4. Build the corresponding React components and hook them into the dashboard/terminal.
5. Write tests using pytest for the backend.
6. Verify no existing routes or types are broken.
```