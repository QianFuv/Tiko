/**
 * Shared frontend types for Tiko API responses and dashboard state.
 */

export type DataSource = "backend" | "demo" | "mixed";

export type ApiData<T> = {
  data: T;
  source: DataSource;
  error: string | null;
};

export type HealthResponse = {
  status: string;
  safety_mode: string;
  private_exchange_methods_allowed: boolean;
  trading_credentials_allowed: boolean;
};

export type BackendHealthState = {
  status: "available" | "unavailable";
  data: HealthResponse | null;
  error: string | null;
};

export type DatasetStatus = "validated" | "invalid";

export type DatasetRecord = {
  dataset_id: string;
  name: string;
  source: string;
  source_uri: string;
  symbols: string[];
  timeframes: string[];
  candle_count: number;
  status: DatasetStatus;
  start_time: string | null;
  end_time: string | null;
  created_at: string;
};

export type DatasetQualityIssue = {
  index: number;
  severity: "error" | "warning";
  code: string;
  message: string;
  symbol: string;
  open_time: string;
};

export type DatasetQualityReport = {
  dataset_id: string;
  total_records: number;
  error_count: number;
  warning_count: number;
  has_errors: boolean;
  issues: DatasetQualityIssue[];
};

export type ExperimentStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "failed";

export type ExperimentRecord = {
  experiment_id: string;
  name: string;
  kind: string;
  hypothesis: string;
  dataset_id: string;
  model_id: string | null;
  parameters: Record<string, unknown>;
  status: ExperimentStatus;
  metrics: Record<string, unknown>;
  created_at: string;
  queued_at: string | null;
  completed_at: string | null;
};

export type SimAccount = {
  account_id: string;
  name: string;
  base_currency: string;
  initial_equity: string;
  cash_balance: string;
  total_equity: string;
  realized_pnl: string;
  unrealized_pnl: string;
  max_drawdown: string;
  status: string;
};

export type SimulationRun = {
  run_id: string;
  name: string;
  status: string;
  mode: string;
  account: SimAccount;
  symbols: string[];
  start_sim_time: string;
  current_sim_time: string;
  end_sim_time: string | null;
  speed_multiplier: string;
  config: Record<string, unknown>;
  created_at: string;
};

export type TradeIntent = {
  decision_id: string;
  run_id: string;
  agent_id: string;
  symbol: string;
  market_type: string;
  action: string;
  target_weight: string;
  target_notional: string | null;
  max_leverage: string;
  confidence: number;
  expected_holding_period: string;
  thesis: string;
  evidence: Record<string, unknown>[];
  invalidation_conditions: string[];
  data_quality_score: number;
  created_at_sim_time: string;
};

export type SimOrder = {
  order_id: string;
  run_id: string;
  account_id: string;
  decision_id: string | null;
  symbol: string;
  side: string;
  order_type: string;
  quantity: string;
  limit_price: string | null;
  status: string;
  submitted_at_sim_time: string;
  updated_at_sim_time: string;
};

export type Fill = {
  fill_id: string;
  order_id: string;
  run_id: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  fee: string;
  slippage_bps: string;
  filled_at_sim_time: string;
};

export type PortfolioSummary = {
  run_id: string;
  base_currency: string;
  cash_balance: string;
  total_equity: string;
  realized_pnl: string;
  unrealized_pnl: string;
  max_drawdown: string;
  gross_exposure: string;
};

export type PositionView = {
  positionId: string;
  accountId: string;
  symbol: string;
  side: "long" | "short" | "flat";
  quantity: string;
  avgEntryPrice: string;
  markPrice: string;
  notional: string;
  leverage: string;
  unrealizedPnl: string;
  realizedPnl: string;
  liquidationPrice: string | null;
  updatedAtSimTime: string;
};

export type RiskLimits = {
  run_id: string;
  minimum_confidence: number;
  minimum_data_quality_score: number;
  max_target_weight: string;
  max_order_notional: string;
  live_trading_allowed: boolean;
};

export type RiskReview = {
  review_id: string;
  decision_id: string;
  status: string;
  original_target_weight: string;
  approved_target_weight: string;
  max_order_notional: string;
  reasons: string[];
  triggered_rules: string[];
  created_at_sim_time: string;
};

export type RunDashboardData = {
  apiBaseUrl: string;
  source: DataSource;
  health: BackendHealthState;
  run: SimulationRun;
  decisions: TradeIntent[];
  orders: SimOrder[];
  fills: Fill[];
  portfolioSummary: PortfolioSummary;
  positions: PositionView[];
  riskLimits: RiskLimits;
  latestRiskReview: RiskReview | null;
};

export type Metric = {
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "good" | "warn" | "danger";
};
