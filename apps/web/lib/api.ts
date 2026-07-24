const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CandleResponse = {
  symbol: string;
  timeframe: string;
  candles: Candle[];
  latest_candle_timestamp: string | null;
  data_freshness: "FRESH" | "STALE" | "UNKNOWN";
};

export type GateResultOut = {
  name: string;
  status: string;
  score: number;
  weight: number;
  confidence: number;
  reason: string;
  evidence: Record<string, unknown>;
};

export type OpinionOut = {
  role: string;
  status: string;
  direction: string;
  confidence: number;
  role_weight: number;
  confidence_cap: number;
  reason: string;
  risk_flags: string[];
  evidence_ids: string[];
};

export type DecisionOut = {
  final_state: string;
  gate_score: number;
  model_score: number;
  composite_score: number;
  model_agreement: number;
  data_completeness: number;
  model_completeness: number;
  vetoes: string[];
  veto_sources: string[];
  reason: string;
  confluence_result?: ConfluenceResult | null;
};

export type DebateMember = {
  name: string;
  confidence: number;
  weight: number;
  reasoning: string;
  low_conviction: boolean;
  source: "gate" | "council" | "news";
};

export type DebateCamp = {
  members: DebateMember[];
  summary: string;
  total_weight: number;
};

export type DebateNewsSentiment = {
  sentiment_label: string | null;
  mean_compound: number | null;
  bullish: number;
  bearish: number;
  total_articles: number;
  macro_label: string | null;
  macro_compound: number | null;
  top_headlines: string[];
};

export type ConfluenceResult = {
  score: number;
  raw_score: number;
  mtf_bonus: number;
  band: "STRONG" | "MODERATE" | "WEAK" | "DIVERGENT";
  direction: string;
  is_actionable: boolean;
  regime: string | null;
  scenario: { primary: string; alternative: string; invalidation: string };
  kelly: { win_probability: number; win_loss_ratio: number; full_kelly: number; half_kelly: number; quarter_kelly: number };
  gate_contributions: Record<string, number>;
  adjusted_weights: Record<string, number>;
  debate?: {
    bull: DebateCamp;
    bear: DebateCamp;
    neutral: DebateCamp;
    scenario: { primary: string; alternative: string; invalidation: string };
    low_conviction_flags: string[];
    debate_summary: string;
    news_sentiment?: DebateNewsSentiment | null;
  };
};

export type TradePlanOut = {
  direction: string;
  entry_price: number | null;
  stop_price: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  position_size_pct: number | null;
  invalidation: string;
  risk_review: string;
  synthesis: string;
};

export type RunOut = {
  id: number;
  symbol: string;
  timeframe: string;
  status: string;
  final_state: string | null;
  config_id: number;
  started_at: string;
  completed_at: string | null;
  note: string | null;
  decision: DecisionOut | null;
  gates: GateResultOut[];
  opinions: OpinionOut[];
  trade_plan: TradePlanOut | null;
};

export type JournalEntry = {
  id: number;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number | null;
  qty: number;
  opened_at: string;
  closed_at: string | null;
  pnl: number | null;
  notes: string;
  analysis_run_id: number | null;
  order_id: number | null;
  created_at: string;
};

export type UserMe = {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
};

export type StrategyConfig = {
  id: number;
  name: string;
  version: number;
  is_active: boolean;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ScanResult = {
  symbol: string;
  timeframe: string;
  final_state: string | null;
  run_id: number;
  started_at: string;
};

export type ScanStatus = {
  running: boolean;
  started_at: string | null;
  completed: number;
  total: number;
  current: string | null;
  notable: ScanResult[];
};

export type TradesConfig = {
  live_trading: boolean;
  max_notional_usd: number;
};

export type OrderOut = {
  id: number;
  exchange: string;
  symbol: string;
  side: string;
  order_type: string;
  qty: number;
  price: number | null;
  status: string;
  exchange_order_id: string | null;
  created_at: string;
  submitted_at: string | null;
  filled_at: string | null;
  raw_response: Record<string, unknown>;
};

const TOKEN_KEY = "confluence_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token == null) window.localStorage.removeItem(TOKEN_KEY);
  else window.localStorage.setItem(TOKEN_KEY, token);
}

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
  parseJson = true,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.headers ?? {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const fetchInit: RequestInit = { method: init.method ?? "GET", headers };
  if (init.body !== undefined && init.body !== null) {
    if (init.body instanceof FormData) {
      fetchInit.body = init.body;
    } else if (typeof init.body === "string") {
      fetchInit.body = init.body;
    } else {
      headers["Content-Type"] = "application/json";
      fetchInit.body = JSON.stringify(init.body);
    }
  }

  const res = await fetch(`${API_BASE_URL}${path}`, fetchInit);
  if (!res.ok) {
    let errBody: unknown = null;
    try {
      errBody = await res.json();
    } catch {
      errBody = await res.text().catch(() => null);
    }
    throw new ApiError(res.status, `HTTP ${res.status}`, errBody);
  }
  if (!parseJson) return undefined as T;
  return (await res.json()) as T;
}

export async function login(email: string, password: string) {
  const data = await request<{ access_token: string; user: UserMe }>(
    "/api/v1/auth/login",
    { method: "POST", body: { email, password } },
  );
  setToken(data.access_token);
  return data.user;
}

export async function register(email: string, password: string) {
  const data = await request<{ access_token: string; user: UserMe }>(
    "/api/v1/auth/register",
    { method: "POST", body: { email, password } },
  );
  setToken(data.access_token);
  return data.user;
}

export async function me(): Promise<UserMe> {
  return request("/api/v1/auth/me");
}

export async function logout() {
  setToken(null);
}

export async function getSymbols(): Promise<string[]> {
  return request("/api/v1/symbols");
}

export async function getCandles(
  symbol: string,
  timeframe: string,
  limit = 300,
): Promise<CandleResponse> {
  return request(
    `/api/v1/market-data/${symbol}/candles?timeframe=${timeframe}&limit=${limit}`,
  );
}

export function getCandlesStreamUrl(symbol: string, timeframe: string): string {
  return `${API_BASE_URL}/api/v1/market-data/${symbol}/stream?timeframe=${timeframe}`;
}

export async function runAnalysis(args: {
  symbol: string;
  timeframe: string;
  strategy?: string;
  config_id?: number;
}): Promise<RunOut> {
  return request("/api/v1/analysis/run", { method: "POST", body: args });
}

export async function listRuns(symbol?: string, limit = 50): Promise<RunOut[]> {
  const qs = new URLSearchParams();
  if (symbol) qs.set("symbol", symbol);
  qs.set("limit", String(limit));
  return request(`/api/v1/analysis/runs?${qs}`);
}

export async function getRun(id: number): Promise<RunOut> {
  return request(`/api/v1/analysis/runs/${id}`);
}

export async function listStrategies(name?: string): Promise<StrategyConfig[]> {
  const qs = name ? `?name=${name}` : "";
  return request(`/api/v1/strategies${qs}`);
}

export async function getActiveStrategy(name = "balanced"): Promise<StrategyConfig | null> {
  return request(`/api/v1/strategies/active?name=${name}`);
}

export async function saveStrategy(args: {
  name: string;
  payload: Record<string, unknown>;
  activate?: boolean;
}): Promise<StrategyConfig> {
  return request("/api/v1/strategies", { method: "POST", body: args });
}

export async function getStrategyPresets(): Promise<{ presets: { name: string; payload: Record<string, unknown> }[] }> {
  return request("/api/v1/strategies/presets");
}

export async function seedDefaults(): Promise<{ seeded: number[] }> {
  return request("/api/v1/strategies/seed-defaults", { method: "POST" });
}

export async function startScan(args: {
  symbols?: string[];
  timeframe?: string;
  strategy?: string;
  candle_limit?: number;
}): Promise<ScanStatus> {
  return request("/api/v1/scanner/run", { method: "POST", body: args });
}

export async function getScanStatus(): Promise<ScanStatus> {
  return request("/api/v1/scanner/status");
}

export async function listLatestScans(limit = 20): Promise<ScanResult[]> {
  return request(`/api/v1/scanner/latest?limit=${limit}`);
}

export async function listJournal(opts: {
  symbol?: string;
  open_only?: boolean;
  limit?: number;
} = {}): Promise<JournalEntry[]> {
  const qs = new URLSearchParams();
  if (opts.symbol) qs.set("symbol", opts.symbol);
  if (opts.open_only) qs.set("open_only", "true");
  if (opts.limit) qs.set("limit", String(opts.limit));
  return request(`/api/v1/journal?${qs}`);
}

export async function createJournalEntry(args: {
  symbol: string;
  side: "LONG" | "SHORT";
  entry_price: number;
  exit_price?: number | null;
  qty: number;
  opened_at: string;
  closed_at?: string | null;
  notes?: string;
  analysis_run_id?: number | null;
  order_id?: number | null;
}): Promise<JournalEntry> {
  return request("/api/v1/journal", { method: "POST", body: args });
}

export async function closeJournalEntry(
  entryId: number,
  exitPrice: number,
  notes?: string,
): Promise<JournalEntry> {
  return request(`/api/v1/journal/${entryId}/close`, {
    method: "POST",
    body: { exit_price: exitPrice, notes: notes ?? "" },
  });
}

export async function deleteJournalEntry(entryId: number): Promise<void> {
  await request(`/api/v1/journal/${entryId}`, { method: "DELETE" }, false);
}

export async function journalSummary(): Promise<{
  total_entries: number;
  open_entries: number;
  closed_entries: number;
  total_pnl: number;
  winners: number;
  losers: number;
}> {
  return request("/api/v1/journal/summary");
}

export type SecFinancialPoint = {
  value: number | null;
  period: string | null;
  form: string | null;
  frame: string | null;
};

export type SecFiling = {
  form: string;
  title: string;
  filing_date: string;
  url: string;
};

export type SecCompanyContext = {
  ticker: string;
  available: boolean;
  reason?: string;
  company_name?: string;
  cik?: string;
  financials?: {
    revenue: SecFinancialPoint | null;
    net_income: SecFinancialPoint | null;
    eps_diluted: SecFinancialPoint | null;
    total_assets: SecFinancialPoint | null;
  };
  recent_filings?: SecFiling[];
  source: string;
};

export async function secContext(ticker: string): Promise<SecCompanyContext> {
  return request(`/api/v1/sec/context?ticker=${encodeURIComponent(ticker)}`);
}

export async function getTradesConfig(): Promise<TradesConfig> {
  return request("/api/v1/trades/config");
}

export async function placeOrder(args: {
  symbol: string;
  side: "BUY" | "SELL";
  order_type?: "MARKET" | "LIMIT";
  qty: number;
  price?: number | null;
  analysis_run_id?: number | null;
  auto_journal?: boolean;
}): Promise<OrderOut> {
  return request("/api/v1/trades/orders", { method: "POST", body: args });
}

export async function listOrders(limit = 50): Promise<OrderOut[]> {
  return request(`/api/v1/trades/orders?limit=${limit}`);
}

export type TickerSnapshot = {
  symbol: string;
  last: number;
  change_24h_pct: number | null;
  high_24h: number | null;
  low_24h: number | null;
  volume_24h: number | null;
  rsi_14: number | null;
  trend: "up" | "down" | "flat";
  sparkline: number[];
};

export type MarketOverview = {
  provider: string;
  as_of: string;
  universe: string[];
  tickers: TickerSnapshot[];
  breadth: { up: number; down: number; flat: number };
  movers: { gainers: TickerSnapshot[]; losers: TickerSnapshot[] };
};

export function getMarketOverview(): Promise<MarketOverview> {
  return request<MarketOverview>("/api/v1/market-overview");
}

export type Venue = { id: string; label: string; enabled: boolean };

export type SymbolSearchResult = {
  symbol: string;
  exchange: string;
  base: string;
  quote: string;
  is_active: boolean;
};

export function listVenues(): Promise<Venue[]> {
  return request<Venue[]>("/api/v1/symbols/venues");
}

export function searchSymbols(q: string): Promise<SymbolSearchResult[]> {
  return request<SymbolSearchResult[]>(`/api/v1/symbols/search?q=${encodeURIComponent(q)}`);
}

export type AnalysisRunSummary = {
  id: number;
  symbol: string;
  timeframe: string;
  status: string;
  final_state: string | null;
  started_at: string;
  completed_at: string | null;
};

export function analysisHistory(symbol: string, limit = 10): Promise<AnalysisRunSummary[]> {
  return request<AnalysisRunSummary[]>(`/api/v1/analysis/runs?symbol=${encodeURIComponent(symbol)}&limit=${limit}`);
}

// ── Backtest ──
export type BacktestRunOut = {
  id: number;
  symbol: string;
  timeframe: string;
  strategy_id: number | null;
  start_date: string;
  end_date: string;
  initial_balance: number;
  final_balance: number | null;
  status: string;
  metrics: Record<string, number | string> | null;
  equity_curve: number[] | null;
  created_at: string;
};

export async function runBacktest(args: {
  symbol: string;
  timeframe?: string;
  strategy_id?: number | null;
  start_date: string;
  end_date: string;
  initial_balance?: number;
  commission_pct?: number;
  slippage_pct?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  lookback?: number;
}): Promise<BacktestRunOut> {
  return request("/api/v1/backtest/run", { method: "POST", body: args });
}

export async function listBacktests(symbol?: string, limit = 50): Promise<BacktestRunOut[]> {
  const qs = new URLSearchParams();
  if (symbol) qs.set("symbol", symbol);
  qs.set("limit", String(limit));
  return request(`/api/v1/backtest?${qs}`);
}

export async function deleteBacktest(runId: number): Promise<void> {
  await request(`/api/v1/backtest/${runId}`, { method: "DELETE" }, false);
}

// ── Liquidity ──
export type LiquidityLevel = {
  price: number;
  intensity: number;
  type: "long_liquidation" | "short_liquidation";
  volume_usd: number;
};

export type LiquidityHeatmap = {
  symbol: string;
  levels: LiquidityLevel[];
  source: string;
  updated_at: string | null;
};

export async function getLiquidityHeatmap(symbol: string): Promise<LiquidityHeatmap> {
  return request(`/api/v1/liquidity/heatmap?symbol=${encodeURIComponent(symbol)}`);
}

export type FundingOI = {
  symbol: string;
  funding: { current: number; predicted: number; annualized: number; trend: string };
  open_interest: { current: number; change_24h: number; change_24h_pct: number; long_short_ratio: number };
  source: string;
};

export async function getFundingOI(symbol: string): Promise<FundingOI> {
  return request(`/api/v1/liquidity/funding-oi?symbol=${encodeURIComponent(symbol)}`);
}

// ── Arbitrage ──
export type YieldOpportunity = {
  symbol: string;
  long_venue: string;
  short_venue: string;
  spot_price: number;
  perp_price: number;
  funding_rate: number;
  net_apy: number;
  confidence: number;
};

export type CexDexSpread = {
  symbol: string;
  cex_venue: string;
  cex_price: number;
  dex_venue: string;
  dex_price: number;
  spread_pct: number;
  net_profit_after_gas: number;
  executable: boolean;
};

export async function getYieldOpportunities(): Promise<{ opportunities: YieldOpportunity[]; count: number }> {
  return request("/api/v1/arbitrage/yield");
}

export async function getCexDexSpreads(): Promise<{ spreads: CexDexSpread[]; count: number }> {
  return request("/api/v1/arbitrage/spreads");
}

// ----- DEX, fundamentals, macro, sentiment -----

export type DexPool = {
  address: string;
  base: string;
  quote: string;
  price: number;
  volume_24h_usd: number;
  liquidity_usd: number;
  fee_tier: number;
};

export type DexNetwork = {
  network: string;
  pool_count: number;
  total_liquidity_usd: number;
  total_volume_24h_usd: number;
  top_pools?: DexPool[];
  tranches?: DexPool[];
};

export async function listDexNetworks(): Promise<{ networks: string[] }> {
  return request("/api/v1/dex/networks");
}

export async function listTopDexPools(network: string, limit = 20): Promise<{ pools: DexPool[] }> {
  return request(`/api/v1/dex/pools/top?network=${network}&limit=${limit}`);
}

export async function getDexPool(poolAddress: string, network = "ethereum"): Promise<Record<string, unknown>> {
  return request(`/api/v1/dex/pools/${poolAddress}?network=${network}`);
}

export async function getDexRange(network = "ethereum"): Promise<DexNetwork> {
  return request(`/api/v1/dex/pools/range?network=${network}`);
}

export async function getDexOverview(): Promise<{ networks: DexNetwork[] }> {
  return request("/api/v1/dex/overview");
}

export async function discoverRobinhoodTranches(): Promise<DexNetwork> {
  return request("/api/v1/dex/tranches/robinhood-base");
}

export async function getDexQuote(
  tokenIn: string, tokenOut: string, amountIn: number, network = "ethereum",
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ token_in: tokenIn, token_out: tokenOut, amount_in: String(amountIn), network });
  return request(`/api/v1/dex/quote?${params.toString()}`);
}

export async function getFundamentalsSnapshot(symbol: string): Promise<Record<string, unknown>> {
  return request(`/api/v1/fundamentals/free/snapshot?symbol=${symbol}`);
}

export async function getFearAndGreed(): Promise<Record<string, unknown>> {
  return request("/api/v1/fundamentals/free/fear-and-greed");
}

export async function getMacroSnapshot(): Promise<Record<string, unknown>> {
  return request("/api/v1/macro/snapshot");
}

export async function getSentiment(symbol: string): Promise<Record<string, unknown>> {
  return request(`/api/v1/sentiment/${encodeURIComponent(symbol)}`);
}

export { ApiError, request };

// ── Intel API (token safety, trenches, whales, sentiment) ──

export type TokenSafety = {
  address: string;
  chain_id: number;
  is_honeypot: boolean | null;
  buy_tax: number | null;
  sell_tax: number | null;
  is_mintable: boolean | null;
  can_take_back_ownership: boolean | null;
  owner_change_balance: boolean | null;
  is_proxy: boolean | null;
  holder_count: number | null;
  total_supply: number | null;
  lp_holders_count: number | null;
  is_open_source: boolean | null;
  is_blacklisted: boolean | null;
  slippage_modifiable: boolean | null;
  risk_level: string;
  risk_flags: string[];
  source: string;
};

export type TrenchPair = {
  chain: string;
  dex: string;
  base_token?: string;
  quote_token?: string;
  price_usd?: number;
  volume_24h?: number;
  volume_6h?: number;
  volume_1h?: number;
  price_change_24h?: number;
  price_change_6h?: number;
  liquidity_usd?: number;
  fdv?: number;
  pair_created_at?: number;
  url?: string;
  token_address?: string;
  description?: string;
  source: string;
};

export type TrendingCoin = {
  name: string;
  symbol: string;
  market_cap_rank: number | null;
  price_btc: number | null;
  score: number | null;
  thumb: string;
  source: string;
};

export type WhaleMovement = {
  tx_hash: string;
  btc_amount: number;
  usd_estimate: number;
  inputs: number;
  outputs: number;
  time: number | null;
  source: string;
};

export async function getTokenSafety(address: string, chainId = 1): Promise<TokenSafety> {
  return request(`/api/v1/intel/token-safety?address=${encodeURIComponent(address)}&chain_id=${chainId}`);
}

export async function getTrenches(limit = 20, chain = "all", hideStable = true): Promise<{ pairs: TrenchPair[]; trending_coins: TrendingCoin[] }> {
  return request(`/api/v1/intel/trenches?limit=${limit}&chain=${chain}&hide_stable=${hideStable}`);
}

export async function getWhaleMovements(minBtc = 100, limit = 20): Promise<{ movements: WhaleMovement[]; count: number }> {
  return request(`/api/v1/intel/whale-movements?min_btc=${minBtc}&limit=${limit}`);
}

export async function getIntelSentiment(): Promise<{ current: Record<string, unknown> | null; history: Record<string, unknown>[] }> {
  return request("/api/v1/intel/sentiment");
}

// ── Derivatives / charting signals (Binance vision — works in geo-blocked regions) ──

export type HeatmapBand = {
  price: number;
  long_score: number;
  short_score: number;
  total_score: number;
};

export type TradeSignal = {
  time: number;
  side: "buy" | "sell";
  entry: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  ema_fast: number;
  ema_slow: number;
  rsi: number;
};

export async function getDerivHeatmap(symbol: string): Promise<{ bands: HeatmapBand[]; current_price: number | null; source: string }> {
  const pair = symbol.replace("/", "").toUpperCase();
  return request(`/api/v1/derivatives/liquidation-heatmap?symbol=${pair}`);
}

export async function getDerivFunding(symbol: string): Promise<{ rows: { time: number; funding_rate: number }[]; source: string; note?: string }> {
  const pair = symbol.replace("/", "").toUpperCase();
  return request(`/api/v1/derivatives/funding?symbol=${pair}`);
}

export async function getDerivOI(symbol: string): Promise<{ rows: { time: number; sum_open_interest: number; sum_open_interest_value: number }[]; source: string; note?: string }> {
  const pair = symbol.replace("/", "").toUpperCase();
  return request(`/api/v1/derivatives/open-interest?symbol=${pair}`);
}

export async function getChartSignals(symbol: string, interval: string): Promise<{ signals: TradeSignal[]; candles: Record<string, unknown>[]; source: string }> {
  const pair = symbol.replace("/", "").toUpperCase();
  return request(`/api/v1/charting/signals?symbol=${pair}&interval=${interval}`);
}

export async function getPinescript(): Promise<{ name: string; script: string }> {
  return request("/api/v1/charting/pinescript");
}

export async function getArbScan(symbol: string): Promise<{ markets: Record<string, unknown>[]; opportunities: Record<string, unknown>[]; source: string }> {
  const base = symbol.replace("/USDT", "").replace("/usdt", "");
  return request(`/api/v1/arbitrage/scan?symbol=${encodeURIComponent(base)}`);
}

// ── DEX sniping / tranches / wallet ──

export async function getSnipeTrending(network = "ethereum", limit = 10): Promise<{ network: string; pools: Record<string, unknown>[] }> {
  return request(`/api/v1/dex/snipe/trending?network=${network}&limit=${limit}`);
}

export async function getTranches(network = "ethereum", hideStable = true): Promise<Record<string, unknown>> {
  return request(`/api/v1/dex/tranches/analyze?network=${network}&hide_stable_pairs=${hideStable}`);
}

export async function analyzeWallet(address: string, chains = "eth,base,arbitrum,optimism,polygon"): Promise<Record<string, unknown>> {
  return request(`/api/v1/council/wallets/${address}/analyze?chains=${chains}`);
}
