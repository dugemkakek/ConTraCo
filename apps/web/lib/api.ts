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

export { ApiError, request };
