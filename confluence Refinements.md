# Confluence Trading Consultant — Master Refinement Plan

## Executive Assessment (200-Year Quant Perspective)

Your foundation is solid — auth, charting, a 6-gate + 6-council analysis pipeline, paper trading, and a journal. But right now this is a **chart reader with opinions**, not a **trading brain**. A real trading brain has three pillars your system is missing or under-developing:

1. **Information Ingestion** — You analyze candles but ignore the world. No news, no sentiment, no economic calendar, no on-chain data, no funding rates. You're trading blind to context.
2. **Multi-Timeframe & Structural Intelligence** — You analyze one timeframe at a time. Real traders form bias on HTF, structure on MTF, entries on LTF. Your gates don't do Wyckoff, SMC, volume profile, or harmonic patterns.
3. **Risk & Performance Engineering** — No position sizing engine, no portfolio heat, no drawdown circuit breakers, no backtesting, no equity curve analytics. You can't improve what you can't measure.

Below is a **10-phase plan** ordered by impact. Each phase is self-contained and can be fed to a coding assistant independently.

---

## PHASE 10: Fundamental Intelligence Layer (News, Sentiment, Calendar)

**Why first:** Every other analysis is context-blind without this. A perfect chart pattern into an FOMC announcement is a coin flip.

### 10.1 — News & RSS Aggregation Service

**New files:**
```
apps/api/app/services/fundamentals/
├── __init__.py
├── news_aggregator.py      # RSS + NewsAPI + CryptoPanic
├── sentiment_analyzer.py   # LLM-based sentiment scoring
├── economic_calendar.py    # ForexFactory / Investing.com scraper or API
├── onchain_metrics.py      # Glassnode/CoinGlass API adapter
├── funding_rates.py        # Perpetual funding rate tracker
└── context_builder.py      # Assembles "fundamental context" blob for LLM council
```

**New API routes:**
```
apps/api/app/api/fundamentals.py
  GET  /api/v1/fundamentals/news?symbol=&hours=24
  GET  /api/v1/fundamentals/sentiment?symbol=
  GET  /api/v1/fundamentals/calendar?days=7
  GET  /api/v1/fundamentals/onchain?symbol=BTC
  GET  /api/v1/fundamentals/funding?symbol=
  GET  /api/v1/fundamentals/context?symbol=&timeframe=   # Composite blob
```

**New DB models (append to `db/models.py`):**
```python
class NewsItem(Base):
    __tablename__ = "news_items"
    id, source, title, url, published_at, symbol_relevance, sentiment_score, summary, created_at

class EconomicEvent(Base):
    __tablename__ = "economic_events"
    id, event_name, country, currency, impact(high/med/low), actual, forecast, previous, event_time, created_at

class FundingRate(Base):
    __tablename__ = "funding_rates"
    id, symbol, venue, rate, timestamp, created_at

class OnChainMetric(Base):
    __tablename__ = "onchain_metrics"
    id, symbol, metric_name, value, timestamp, created_at
```

**Implementation details:**

`news_aggregator.py`:
- Use `feedparser` for RSS feeds (CoinDesk, CoinTelegraph, Reuters crypto, Bloomberg crypto)
- Use NewsAPI.org free tier (100 req/day) as secondary
- Use CryptoPanic API for crypto-specific news
- Deduplicate by URL hash
- Tag each article with relevant symbols using keyword matching + LLM fallback
- Cache results in Redis with 15-min TTL
- Background task: `asyncio.create_task` polling every 10 minutes

`sentiment_analyzer.py`:
- For each news item, call LLM with prompt: "Rate sentiment for {symbol} as -1.0 to +1.0 based on this headline and summary: {text}"
- Batch process with `asyncio.gather` (max 5 concurrent)
- Compute rolling 24h sentiment score per symbol (weighted by recency)
- Store in Redis: `sentiment:{symbol}:24h` → float

`economic_calendar.py`:
- Use ForexFactory calendar RSS or investing.com API
- Parse high-impact events (FOMC, CPI, NFP, GDP, rate decisions)
- Flag events within ±2 hours as "ACTIVE RISK"
- This feeds into the `risk_tradeability` gate

`funding_rates.py`:
- Poll Gate.io `/futures/usdt/contracts/{contract}/funding_rate` every 5 min
- Also fetch from Binance for cross-reference
- Extreme funding (>0.1% or <-0.1%) = contrarian signal
- Feed into `volume_momentum` gate

`onchain_metrics.py`:
- CoinGlass API (free tier): exchange net flow, long/short ratio, open interest
- Glassnode (if key available): active addresses, exchange reserve
- Whale alert webhook listener (optional)

`context_builder.py`:
- Assembles a structured text blob:
```
FUNDAMENTAL CONTEXT for BTCUSDT (as of 2025-01-15 14:30 UTC):
- 24h News Sentiment: +0.34 (moderately bullish) — 12 articles
- Top Headline: "BlackRock Bitcoin ETF sees $500M inflow" (sentiment: +0.8)
- Economic Events Next 24h: US CPI (HIGH impact, 13:30 UTC) ⚠️
- Funding Rate: +0.012% (neutral)
- Open Interest Change 24h: +4.2% (increasing leverage)
- Exchange Net Flow: -2,400 BTC (outflow = bullish)
- RISK FLAG: High-impact economic event in 2h — reduce position size
```
- This blob is injected into every LLM council role's prompt

**Modify existing files:**

`engine/gates/risk_tradeability.py` — Add check:
```python
# If high-impact economic event within 2 hours, cap score at 0.3
# If funding rate extreme, add contrarian warning
```

`engine/council.py` — Inject `fundamental_context` into each role's system prompt

`llm/prompts.py` — Add `{fundamental_context}` placeholder to all 6 role prompts

`engine/runner.py` — Before running gates, call `context_builder.build_context(symbol)` and pass through pipeline

**New env vars:**
```
NEWSAPI_KEY=...
CRYPTOPANIC_TOKEN=...
COINGLASS_API_KEY=...
GLASSNODE_API_KEY=...        # optional
```

**New dependencies (requirements.txt / pyproject.toml):**
```
feedparser>=6.0
httpx>=0.27          # already likely present
```

---

## PHASE 11: Multi-Timeframe Confluence Engine

**Why:** Single-timeframe analysis is amateur hour. Professional traders use HTF bias → MTF structure → LTF entry.

### 11.1 — MTF Analysis Orchestrator

**New files:**
```
apps/api/app/engine/mtf/
├── __init__.py
├── timeframe_hierarchy.py   # Defines TF relationships
├── mtf_runner.py            # Runs analysis across 3 TFs
├── confluence_scorer.py     # Scores alignment across TFs
└── bias_resolver.py         # Resolves conflicts between TFs
```

**`timeframe_hierarchy.py`:**
```python
TIMEFRAME_HIERARCHY = {
    "scalp": {
        "entry": ["1m", "5m"],
        "structure": ["15m"],
        "bias": ["1h", "4h"],
    },
    "intraday": {
        "entry": ["5m", "15m"],
        "structure": ["1h"],
        "bias": ["4h", "1d"],
    },
    "swing": {
        "entry": ["1h", "4h"],
        "structure": ["4h", "1d"],
        "bias": ["1d", "1w"],
    },
}
```

**`mtf_runner.py`:**
- Given a symbol + strategy type, determine the 3 relevant timeframes
- Run the existing gate pipeline on each TF in parallel (`asyncio.gather`)
- Collect gate scores per TF
- Pass all 3 TF results to `confluence_scorer`

**`confluence_scorer.py`:**
- If all 3 TFs agree on direction → score multiplier 1.5x
- If 2/3 agree → multiplier 1.0x
- If HTF disagrees with entry TF → multiplier 0.5x + warning "Counter-trend trade"
- If HTF is neutral → multiplier 0.8x
- Output: `mtf_confluence_score`, `mtf_alignment` (full/partial/conflicting), `mtf_details`

**`bias_resolver.py`:**
- When TFs conflict, apply rules:
  - HTF always wins for direction bias
  - Entry TF only determines timing
  - If HTF bearish + entry TF bullish → "pullback long in downtrend" (lower confidence)

**Modify `engine/runner.py`:**
```python
# After single-TF analysis, optionally run MTF
if strategy.mtf_enabled:
    mtf_result = await mtf_runner.run_mtf_analysis(symbol, strategy.type, provider)
    decision.mtf_confluence = mtf_result.confluence_score
    decision.mtf_alignment = mtf_result.alignment
    # Adjust final composite score
    decision.final_score *= mtf_result.multiplier
```

**Modify `schemas/`:**
```python
class MTFResult(BaseModel):
    timeframes: dict[str, GateScores]
    confluence_score: float
    alignment: str  # "full" | "partial" | "conflicting"
    multiplier: float
    bias: str  # "bullish" | "bearish" | "neutral"
    details: str  # Human-readable summary
```

**Frontend additions:**
```
web/components/decision/MTFConfluence.tsx
  - Shows 3 timeframe cards with directional arrows
  - Color-coded: green=aligned, yellow=partial, red=conflicting
  - Displays multiplier effect on final score
```

**Modify `web/components/decision/AnalysisTabs.tsx`:**
- Add "MTF" tab showing the multi-timeframe breakdown

---

## PHASE 12: Advanced Technical Analysis Gates

**Why:** Your 6 gates cover basics. Missing: market structure (SMC), volume profile, Wyckoff, harmonic patterns, Ichimoku. These are what separate retail from institutional analysis.

### 12.1 — New Gates

**New files in `engine/gates/`:**
```
├── market_structure_smc.py    # BOS, CHoCH, FVG, Order Blocks
├── volume_profile.py          # VPVR, POC, Value Area
├── wyckoff_phase.py           # Accumulation/Distribution phases
├── harmonic_patterns.py       # Gartley, Bat, Butterfly, Crab
├── ichimoku_cloud.py          # Cloud, TK cross, Chikou
└── fibonacci_levels.py        # Retracement + extension levels
```

**`market_structure_smc.py` (Smart Money Concepts):**
```python
def evaluate(candles: list[Candle]) -> GateResult:
    # 1. Identify swing highs/lows (pivot points, lookback=5)
    # 2. Detect Break of Structure (BOS): price breaks previous swing high in uptrend
    # 3. Detect Change of Character (CHoCH): trend reversal signal
    # 4. Identify Fair Value Gaps (FVG): 3-candle imbalance where wick1.high < wick3.low
    # 5. Identify Order Blocks: last bearish candle before bullish BOS (and vice versa)
    # 6. Score:
    #    - BOS in trade direction: +0.3
    #    - CHoCH against trade: -0.4 (warning)
    #    - Price at FVG (potential support/resistance): +0.2
    #    - Price at Order Block: +0.2
    # Return GateResult with score, details, key_levels[]
```

**`volume_profile.py`:**
```python
def evaluate(candles: list[Candle]) -> GateResult:
    # 1. Build volume profile: bin prices into N levels (e.g., 50 bins)
    # 2. Sum volume per bin
    # 3. Find POC (Point of Control) = highest volume bin
    # 4. Find Value Area High/Low (70% of volume)
    # 5. Score:
    #    - Price at POC: neutral (chop zone) → score 0.3
    #    - Price at VAH with bullish momentum: breakout signal → 0.7
    #    - Price at VAL with bearish momentum: breakdown signal → 0.7 (short)
    #    - Price outside value area: trending → 0.6
    # Return key levels: POC, VAH, VAL
```

**`wyckoff_phase.py`:**
```python
def evaluate(candles: list[Candle]) -> GateResult:
    # Simplified Wyckoff detection:
    # 1. Identify trading range (consolidation > 20 candles, range < 5%)
    # 2. Within range, detect phases:
    #    Phase A: Stopping volume (high vol candle at range low)
    #    Phase B: Building cause (oscillation within range)
    #    Phase C: Spring/test (brief break below range, quick reclaim)
    #    Phase D: Markup begins (break above range with volume)
    #    Phase E: Trend continuation
    # 3. Score based on phase:
    #    Phase C spring detected → high conviction long (0.8)
    #    Phase D breakout → confirmation long (0.7)
    #    Phase B → neutral, wait (0.3)
    #    Distribution detected → bearish (0.2 for longs)
```

**`harmonic_patterns.py`:**
```python
def evaluate(candles: list[Candle]) -> GateResult:
    # 1. Find 5-point swing patterns (XABCD)
    # 2. Check Fibonacci ratios for each pattern type:
    #    Gartley: AB=0.618 XA, BC=0.382-0.886 AB, CD=1.272-1.618 BC, AD=0.786 XA
    #    Bat: AD=0.886 XA
    #    Butterfly: AD=1.272 XA
    #    Crab: AD=1.618 XA
    # 3. If pattern completing at D point → high conviction reversal signal
    # 4. Score: 0.7-0.9 if pattern valid + at completion point
```

**`ichimoku_cloud.py`:**
```python
def evaluate(candles: list[Candle]) -> GateResult:
    # Standard Ichimoku: Tenkan(9), Kijun(26), SenkouA, SenkouB(52), Chikou(26)
    # Bullish: price > cloud, Tenkan > Kijun, Chikou > price 26 ago, future cloud green
    # Bearish: inverse
    # Score: count bullish conditions / 4 → 0.0 to 1.0
```

**`fibonacci_levels.py`:**
```python
def evaluate(candles: list[Candle]) -> GateResult:
    # 1. Find most recent significant swing high/low
    # 2. Calculate retracement levels: 0.236, 0.382, 0.5, 0.618, 0.786
    # 3. Calculate extension levels: 1.272, 1.618, 2.0, 2.618
    # 4. Score: if price at key Fib level + bouncing → 0.7
    # 5. Return key levels for chart overlay
```

### 12.2 — Register New Gates

**Modify `engine/gates/__init__.py`:**
```python
GATE_REGISTRY = {
    # existing 6
    "market_regime": MarketRegimeGate,
    "market_structure": MarketStructureGate,
    "volume_momentum": VolumeMomentumGate,
    "classical_ta": ClassicalTAGate,
    "risk_tradeability": RiskTradeabilityGate,
    "fundamental": FundamentalGate,
    # new 6
    "smc_structure": SMCStructureGate,
    "volume_profile": VolumeProfileGate,
    "wyckoff_phase": WyckoffPhaseGate,
    "harmonic_patterns": HarmonicPatternsGate,
    "ichimoku_cloud": IchimokuCloudGate,
    "fibonacci_levels": FibonacciLevelsGate,
}
```

**Modify `engine/decision.py`:**
- Update composite scoring to include 12 gates
- Rebalance weights (technical gates 60%, structural 25%, fundamental 15%)

**Modify `engine/strategy.py`:**
- Strategy config now selects which gates to enable (not all 12 always on)
- Default strategies:
  - `scalp_smc`: smc_structure + volume_profile + classical_ta + volume_momentum + risk_tradeability
  - `swing_wyckoff`: wyckoff_phase + fibonacci_levels + ichimoku_cloud + market_regime + fundamental + risk_tradeability
  - `full_confluence`: all 12 gates

**Frontend:**
- `GateScores.tsx` — Expand to show 12 gates, grouped by category
- Chart overlay: Draw Fibonacci levels, FVG boxes, Order Blocks, VPVR on TradingView chart via `createShape` API

---

## PHASE 13: Risk Management Engine

**Why:** This is what keeps traders alive. No position sizing, no drawdown limits, no portfolio heat = gambling.

### 13.1 — Position Sizing & Risk Calculator

**New files:**
```
apps/api/app/engine/risk/
├── __init__.py
├── position_sizer.py        # Kelly, fixed fractional, ATR-based
├── portfolio_heat.py        # Total exposure tracking
├── drawdown_guard.py        # Daily/weekly loss limits
├── correlation_risk.py      # Inter-position correlation
└── risk_report.py           # Pre-trade risk summary
```

**`position_sizer.py`:**
```python
def calculate_size(
    account_balance: float,
    entry_price: float,
    stop_price: float,
    risk_pct: float = 1.0,        # Default 1% risk per trade
    method: str = "fixed_fractional",  # or "kelly" or "atr"
    atr_value: float = None,
    atr_multiplier: float = 2.0,
    win_rate: float = None,        # For Kelly
    avg_win_loss_ratio: float = None,  # For Kelly
) -> PositionSize:
    """
    fixed_fractional: size = (balance * risk_pct) / |entry - stop|
    kelly: f* = (win_rate * avg_win_loss_ratio - (1 - win_rate)) / avg_win_loss_ratio
           then use half-Kelly for safety
    atr: stop_distance = atr * atr_multiplier, then fixed_fractional
    """
```

**`drawdown_guard.py`:**
```python
class DrawdownGuard:
    def __init__(self, daily_max_loss_pct=3.0, weekly_max_loss_pct=6.0, max_consecutive_losses=3):
        ...

    async def check(self, user_id: int) -> DrawdownStatus:
        # Query journal for today's realized PnL
        # If daily loss > 3% → CIRCUIT BREAKER: block new trades
        # If weekly loss > 6% → REDUCE: halve position sizes
        # If consecutive losses >= 3 → COOLDOWN: require manual override
        # Return status: "green" | "yellow" | "red"
```

**`portfolio_heat.py`:**
```python
async def calculate_heat(user_id: int) -> PortfolioHeat:
    # Sum of risk% across all open positions
    # If total heat > 6% → warning
    # If total heat > 10% → block new trades
    # Breakdown by symbol, by direction
```

**`correlation_risk.py`:**
```python
async def check_correlation(new_symbol: str, open_positions: list) -> CorrelationWarning:
    # If opening BTC long and already have ETH long → correlated exposure
    # Use 30-day rolling correlation from price data
    # If correlation > 0.7 → warn "highly correlated, effective exposure doubled"
```

**New API routes:**
```
apps/api/app/api/risk.py
  GET  /api/v1/risk/position-size?symbol=&entry=&stop=&method=
  GET  /api/v1/risk/heat
  GET  /api/v1/risk/drawdown-status
  GET  /api/v1/risk/pre-trade-check?symbol=&side=&entry=&stop=&size=
  GET  /api/v1/risk/correlation?symbol=
```

**Modify `engine/trade_plan.py`:**
- Before generating trade plan, run `drawdown_guard.check()`
- Include position size calculation in trade plan output
- Include risk-reward ratio (must be ≥ 1.5:1 or flag warning)

**Modify `api/trades.py`:**
- Before placing paper order, run full `pre_trade_check`
- Reject if drawdown guard is red
- Reject if portfolio heat > 10%

**Frontend:**
```
web/components/risk/
├── PositionSizer.tsx       # Interactive calculator widget
├── DrawdownGauge.tsx       # Circular gauge: daily/weekly loss
├── PortfolioHeatMap.tsx    # Visual heat display
├── PreTradeChecklist.tsx   # Green/yellow/red checklist before trade
└── CorrelationMatrix.tsx   # Heatmap of open position correlations
```

**New DB model:**
```python
class RiskConfig(Base):
    __tablename__ = "risk_configs"
    id, user_id, risk_per_trade_pct, daily_max_loss_pct, weekly_max_loss_pct,
    max_consecutive_losses, max_portfolio_heat_pct, min_rr_ratio,
    sizing_method, is_active, created_at
```

---

## PHASE 14: Backtesting Engine

**Why:** Without backtesting, you're deploying untested strategies with real money. This is non-negotiable.

### 14.1 — Historical Backtest Framework

**New files:**
```
apps/api/app/engine/backtest/
├── __init__.py
├── data_loader.py           # Load historical OHLCV from provider or DB cache
├── backtest_runner.py       # Main loop: iterate candles, apply strategy
├── gate_simulator.py        # Run gates on historical candle windows
├── execution_simulator.py   # Simulate fills with slippage + commission
├── metrics_calculator.py    # Sharpe, Sortino, max DD, win rate, expectancy
├── walk_forward.py          # Walk-forward optimization
└── report_generator.py      # Generate backtest report
```

**`backtest_runner.py`:**
```python
async def run_backtest(
    symbol: str,
    timeframe: str,
    strategy_id: int,
    start_date: datetime,
    end_date: datetime,
    initial_balance: float = 10000.0,
    commission_pct: float = 0.1,    # 0.1% per trade
    slippage_pct: float = 0.05,     # 0.05% slippage
) -> BacktestResult:
    # 1. Load historical candles (from Gate.io or cached DB)
    # 2. For each candle window (lookback period):
    #    a. Run enabled gates on window
    #    b. If composite score > threshold → generate signal
    #    c. If signal → simulate entry at next candle open + slippage
    #    d. Track position: check stop loss / take profit on each subsequent candle
    #    e. On exit → record trade with commission
    # 3. Calculate metrics on all trades
    # 4. Generate equity curve
    # 5. Return BacktestResult
```

**`metrics_calculator.py`:**
```python
def calculate_metrics(trades: list[Trade], equity_curve: list[float]) -> BacktestMetrics:
    return BacktestMetrics(
        total_trades=len(trades),
        win_rate=wins/total,
        profit_factor=gross_profit/gross_loss,
        expectancy=avg_win*win_rate - avg_loss*loss_rate,
        sharpe_ratio=mean(returns)/std(returns) * sqrt(252),
        sortino_ratio=mean(returns)/downside_std * sqrt(252),
        max_drawdown=max peak-to-trough decline,
        max_drawdown_duration=longest time underwater,
        avg_trade_duration=mean(trade durations),
        largest_win=max single trade profit,
        largest_loss=max single trade loss,
        consecutive_wins=max streak,
        consecutive_losses=max streak,
        total_return=(final_equity - initial) / initial,
        annualized_return=...,
        calmar_ratio=annualized_return / max_drawdown,
    )
```

**New API routes:**
```
apps/api/app/api/backtest.py
  POST /api/v1/backtest/run          # Start backtest (async, returns job_id)
  GET  /api/v1/backtest/status/{id}   # Poll status
  GET  /api/v1/backtest/results/{id}  # Full results + equity curve
  GET  /api/v1/backtest/history       # List past backtests
```

**New DB models:**
```python
class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id, user_id, symbol, timeframe, strategy_id, start_date, end_date,
    initial_balance, final_balance, status, metrics_json, equity_curve_json,
    trades_json, created_at

class HistoricalCandle(Base):
    __tablename__ = "historical_candles"
    id, symbol, venue, timeframe, open_time, open, high, low, close, volume
    # Indexed on (symbol, timeframe, open_time) for fast range queries
    # Cache Gate.io historical data to avoid re-fetching
```

**Frontend:**
```
web/app/backtest/page.tsx              # Backtest configuration + results page
web/components/backtest/
├── BacktestConfig.tsx     # Symbol, TF, date range, strategy selector
├── EquityCurve.tsx        # Line chart of equity over time (lightweight-charts)
├── MetricsGrid.tsx        # Key metrics cards
├── TradeList.tsx          # Scrollable list of all trades
├── DrawdownChart.tsx      # Underwater equity chart
└── MonthlyHeatmap.tsx     # Calendar heatmap of daily PnL
```

---

## PHASE 15: Alert & Notification System

**Why:** You can't stare at charts 24/7. The system needs to come to you.

### 15.1 — Alert Engine

**New files:**
```
apps/api/app/services/alerts/
├── __init__.py
├── alert_engine.py          # Evaluates alert conditions on each candle update
├── condition_evaluator.py   # Price, indicator, gate score, pattern conditions
├── notification_dispatcher.py  # Send via channels
├── channels/
│   ├── __init__.py
│   ├── telegram.py          # Telegram Bot API
│   ├── discord.py           # Discord webhook
│   ├── email.py             # SMTP
│   └── websocket_push.py    # Push to frontend via WS
└── templates.py             # Alert message templates
```

**Alert types:**
```python
class AlertCondition(BaseModel):
    type: str  # "price_cross" | "indicator" | "gate_score" | "pattern" | "news" | "scanner"
    symbol: str
    params: dict  # e.g., {"indicator": "RSI", "condition": "cross_above", "value": 70}
    channels: list[str]  # ["telegram", "discord", "browser"]
    cooldown_minutes: int = 60  # Don't re-fire within this window
```

**New API routes:**
```
apps/api/app/api/alerts.py
  GET    /api/v1/alerts                # List user alerts
  POST   /api/v1/alerts                # Create alert
  PUT    /api/v1/alerts/{id}           # Update alert
  DELETE /api/v1/alerts/{id}           # Delete alert
  GET    /api/v1/alerts/history        # Fired alert history
  POST   /api/v1/alerts/{id}/test      # Test fire an alert
```

**Integration with existing streaming:**
- In `gateio_ws.py` (or the SSE stream handler), after each candle close:
  - Run `alert_engine.evaluate(symbol, candle)` for all active alerts on that symbol
  - Fire matching alerts through dispatcher

**New DB model:**
```python
class Alert(Base):  # Extend existing Alert table
    __tablename__ = "alerts"
    id, user_id, symbol, condition_type, condition_params_json,
    channels_json, cooldown_minutes, is_active, last_fired_at, created_at

class AlertHistory(Base):
    __tablename__ = "alert_history"
    id, alert_id, fired_at, message, channels_sent_json, acknowledged
```

**Frontend:**
```
web/app/alerts/page.tsx               # Alert management page
web/components/alerts/
├── AlertBuilder.tsx       # Visual alert condition builder
├── AlertList.tsx          # Active alerts with toggle
├── AlertHistory.tsx       # Past fired alerts
└── NotificationSettings.tsx  # Configure Telegram/Discord/email
```

---

## PHASE 16: Performance Analytics Dashboard

**Why:** The journal exists but lacks analytics. You need to know your edge statistically.

### 16.1 — Analytics Engine

**New files:**
```
apps/api/app/services/analytics/
├── __init__.py
├── trade_analytics.py       # Per-trade statistics
├── strategy_analytics.py    # Per-strategy performance
├── time_analytics.py        # Performance by hour/day/month
├── symbol_analytics.py      # Performance by symbol
└── streak_analytics.py      # Win/loss streak analysis
```

**New API routes:**
```
apps/api/app/api/analytics.py
  GET /api/v1/analytics/overview        # Summary stats
  GET /api/v1/analytics/equity-curve    # Cumulative PnL over time
  GET /api/v1/analytics/by-strategy     # Performance per strategy
  GET /api/v1/analytics/by-symbol       # Performance per symbol
  GET /api/v1/analytics/by-time         # Performance by hour/day
  GET /api/v1/analytics/drawdown        # Drawdown analysis
  GET /api/v1/analytics/distribution    # PnL distribution histogram
  GET /api/v1/analytics/streaks         # Win/loss streak data
```

**Frontend:**
```
web/app/analytics/page.tsx             # Full analytics dashboard
web/components/analytics/
├── EquityCurveChart.tsx    # Cumulative PnL line chart
├── MonthlyReturnsHeatmap.tsx  # Calendar-style heatmap
├── WinRateGauge.tsx        # Circular gauge
├── PnLDistribution.tsx     # Histogram of trade PnLs
├── StrategyComparison.tsx  # Bar chart comparing strategies
├── TimeOfDayChart.tsx      # Performance by hour of day
├── SymbolBreakdown.tsx     # Table of per-symbol stats
└── StreakTracker.tsx       # Current + max streaks
```

---

## PHASE 17: Real-Time WebSocket Dashboard

**Why:** Polling every 30s is unacceptable for a trading terminal. You need sub-second updates.

### 17.1 — WebSocket Hub

**New files:**
```
apps/api/app/services/realtime/
├── __init__.py
├── ws_hub.py              # WebSocket connection manager
├── ws_handler.py          # FastAPI WebSocket endpoint
├── event_bus.py           # Internal pub/sub for events
└── serializers.py         # Event → JSON serialization
```

**`ws_hub.py`:**
```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}  # user_id → connections

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    async def broadcast_to_user(self, user_id: str, event: dict):
        for conn in self.active_connections.get(user_id, []):
            await conn.send_json(event)

    async def broadcast_symbol_update(self, symbol: str, data: dict):
        # Send to all users watching this symbol
        ...
```

**New endpoint:**
```python
# In main.py or a new ws route
@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    user = verify_jwt(token)
    await manager.connect(websocket, str(user.id))
    try:
        while True:
            # Handle subscription messages from client
            data = await websocket.receive_json()
            if data["type"] == "subscribe":
                # Subscribe to symbol updates, alerts, scanner progress
                ...
    except WebSocketDisconnect:
        manager.disconnect(websocket, str(user.id))
```

**Events pushed via WS:**
- `candle_update` — New candle close for subscribed symbols
- `alert_fired` — Alert triggered
- `scanner_progress` — Scanner batch progress
- `analysis_complete` — Analysis run finished
- `order_filled` — Paper order filled
- `drawdown_warning` — Risk threshold breached

**Frontend:**
```
web/lib/ws-client.ts       # WebSocket client with auto-reconnect
web/lib/ws-provider.tsx     # React context for WS
# Modify dashboard to use WS instead of polling
```

---

## PHASE 18: Order Book & Market Depth

**Why:** Price action alone misses the liquidity landscape. Order book reveals support/resistance walls.

### 18.1 — Depth Data & Visualization

**New files:**
```
apps/api/app/services/market_data/orderbook.py   # Fetch order book from provider
apps/api/app/api/orderbook.py                     # API routes
```

**New API routes:**
```
GET /api/v1/market-data/{symbol}/orderbook?depth=20
GET /api/v1/market-data/{symbol}/depth-stream     # SSE depth updates
```

**Frontend:**
```
web/components/chart/DepthChart.tsx    # Bid/ask depth visualization
web/components/terminal/OrderBook.tsx  # Live order book table
```

**Modify `gateio_rest.py`:** Add `get_orderbook(symbol, depth)` method
**Modify `gateio_ws.py`:** Add orderbook subscription channel

---

## PHASE 19: Strategy Templates & Presets

**Why:** Users shouldn't configure 12 gates from scratch. Provide battle-tested presets.

**New file:**
```
apps/api/app/engine/strategy_templates.py
```

**Templates:**
```python
STRATEGY_TEMPLATES = {
    "smc_scalper": {
        "name": "SMC Scalper",
        "description": "Smart Money Concepts for 1m-5m scalps. Uses order blocks, FVGs, and volume profile for entries.",
        "timeframes": ["1m", "5m"],
        "gates": ["smc_structure", "volume_profile", "volume_momentum", "classical_ta", "risk_tradeability"],
        "gate_weights": {"smc_structure": 0.3, "volume_profile": 0.2, "volume_momentum": 0.2, "classical_ta": 0.15, "risk_tradeability": 0.15},
        "score_threshold": 0.65,
        "default_rr": 2.0,
        "mtf_enabled": True,
        "mtf_type": "scalp",
    },
    "wyckoff_swing": {
        "name": "Wyckoff Swing",
        "description": "Wyckoff accumulation/distribution for 4h-1D swings. Patient entries at spring/test points.",
        "timeframes": ["4h", "1d"],
        "gates": ["wyckoff_phase", "fibonacci_levels", "ichimoku_cloud", "market_regime", "fundamental", "risk_tradeability"],
        "gate_weights": {"wyckoff_phase": 0.25, "fibonacci_levels": 0.15, "ichimoku_cloud": 0.15, "market_regime": 0.15, "fundamental": 0.15, "risk_tradeability": 0.15},
        "score_threshold": 0.6,
        "default_rr": 3.0,
        "mtf_enabled": True,
        "mtf_type": "swing",
    },
    "full_confluence": {
        "name": "Full Confluence",
        "description": "All 12 gates. Maximum analysis depth. Slower but most thorough.",
        "timeframes": ["1h"],
        "gates": list(GATE_REGISTRY.keys()),
        "gate_weights": None,  # Equal weights
        "score_threshold": 0.55,
        "default_rr": 2.5,
        "mtf_enabled": True,
        "mtf_type": "intraday",
    },
    "momentum_breakout": {
        "name": "Momentum Breakout",
        "description": "Catches breakouts with volume confirmation. Fast entries on momentum shifts.",
        "timeframes": ["15m", "1h"],
        "gates": ["volume_momentum", "market_structure", "classical_ta", "smc_structure", "risk_tradeability"],
        "score_threshold": 0.7,
        "default_rr": 2.0,
    },
    "mean_reversion": {
        "name": "Mean Reversion",
        "description": "Fades extremes using RSI, Bollinger, and Fibonacci. Best in ranging markets.",
        "timeframes": ["1h", "4h"],
        "gates": ["classical_ta", "fibonacci_levels", "ichimoku_cloud", "market_regime", "risk_tradeability"],
        "score_threshold": 0.65,
        "default_rr": 1.5,
    },
}
```

**New API route:**
```
GET /api/v1/strategies/templates    # List available templates
POST /api/v1/strategies/from-template  # Create strategy from template
```

**Frontend:**
- Settings page: "Create from Template" dropdown with descriptions
- Each template shows which gates it uses, recommended TFs, expected style

---

## PHASE 20: Chart Overlay Integration (Drawing Analysis on Chart)

**Why:** Analysis results should be visual on the chart, not just numbers in a panel.

### 20.1 — TradingView Shape API Integration

**Modify `web/components/chart/TradingViewChart.tsx`:**

After analysis completes, draw on chart:
```typescript
// Fibonacci levels
widget.createMultipointShape(points, { shape: 'horizontal_line', ... });

// FVG boxes
widget.createShape({ time, price }, { shape: 'rectangle', ... });

// Order blocks
widget.createShape({ time, price }, { shape: 'rectangle', ... });

// Support/Resistance levels from gates
widget.createMultipointShape(...);

// Entry/Stop/TP lines from trade plan
widget.createOrderLine(...);  // TradingView order line widget
```

**New API response field:**
```python
class ChartOverlay(BaseModel):
    fib_levels: list[PriceLevel]
    fvg_zones: list[PriceZone]
    order_blocks: list[PriceZone]
    support_resistance: list[PriceLevel]
    entry_line: float | None
    stop_line: float | None
    tp_lines: list[float]
    ichimoku_cloud: list[CloudPoint] | None
```

Each gate returns its `chart_overlay` data, aggregated in `runner.py`, returned in `RunOut`.

---

## Implementation Priority Matrix

| Phase | Impact | Effort | Dependencies | Priority |
|-------|--------|--------|-------------|----------|
| 10: Fundamentals | ★★★★★ | Medium | None | **1st** |
| 13: Risk Engine | ★★★★★ | Medium | None | **2nd** |
| 11: MTF Confluence | ★★★★☆ | Medium | None | **3rd** |
| 12: Advanced Gates | ★★★★☆ | High | None | **4th** |
| 16: Analytics | ★★★★☆ | Medium | Journal (exists) | **5th** |
| 14: Backtesting | ★★★★★ | High | Gates (12) | **6th** |
| 15: Alerts | ★★★☆☆ | Medium | WS (17) | **7th** |
| 17: WebSocket | ★★★☆☆ | Medium | None | **8th** |
| 19: Templates | ★★★☆☆ | Low | Gates (12) | **9th** |
| 20: Chart Overlays | ★★★☆☆ | Medium | Gates (12) | **10th** |
| 18: Order Book | ★★☆☆☆ | Low | Provider | **11th** |

---

## How to Feed This to Your Coding Assistant

For each phase, give the coding assistant this prompt template:

```
You are implementing Phase [N] of the Confluence Trading Consultant project.

EXISTING PROJECT CONTEXT:
- Stack: Python 3.14 + FastAPI backend, Next.js 16 + React 19 + Tailwind frontend
- Charts: TradingView Advanced Chart widget (CDN) + lightweight-charts
- AI: Mineral (ocg/minimax-m3 via InferHub) council of 6 roles + 6 gates
- Data: Mock provider (dev) + Gate.io REST + WS (live)
- DB: SQLite (dev) / Postgres (prod), SQLAlchemy ORM
- [Include the HANDOFF.md content]

PHASE [N] SPECIFICATION:
[Paste the relevant phase section above]

REQUIREMENTS:
1. Create all new files listed
2. Modify existing files as specified (show full diff or complete file)
3. Add new DB models and create Alembic migration
4. Add new API routes and register in main.py
5. Add frontend components and pages
6. Write tests for new backend logic (pytest)
7. Update HANDOFF.md with new endpoints and architecture notes
8. Ensure backward compatibility — existing features must not break

Start with the backend, then frontend, then tests.
```

---

This plan transforms your system from a **chart analyzer with AI opinions** into a **full-spectrum trading brain** that ingests world context, analyzes across timeframes with institutional-grade techniques, manages risk like a fund, validates strategies historically, alerts you in real-time, and tracks your edge statistically. That's the difference between a toy and a weapon.