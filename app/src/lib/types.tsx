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

export type ModelRegistryEntry = {
  model_id: string;
  name: string;
  version: string;
  model_type: string;
  algorithm: string;
  training_dataset_id: string;
  validation_dataset_id: string;
  metrics: Record<string, unknown>;
  artifact_uri: string;
  status: string;
  created_at: string;
};

export type ReportArtifact = {
  report_id: string;
  run_id: string;
  report_type: "simulation" | "decision" | "experiment";
  title: string;
  summary: string;
  sections: Record<string, unknown>;
  created_at_sim_time: string;
  created_at: string;
};

export type AlertCategory =
  | "pnl"
  | "drawdown"
  | "agent_timeout"
  | "data_quality"
  | "order_anomaly"
  | "runtime_stuck"
  | "worker_health"
  | "risk_circuit_breaker"
  | "model_degradation";

export type AlertSeverity = "info" | "warning" | "critical";

export type AlertStatus = "open" | "acknowledged" | "resolved";

export type Alert = {
  alert_id: string;
  run_id: string;
  category: AlertCategory;
  severity: AlertSeverity;
  message: string;
  status: AlertStatus;
  created_at_sim_time: string;
  created_at: string;
};

export type MarketSymbolsResponse = {
  symbols: string[];
  data_policy: string;
  private_methods_allowed: boolean;
};

export type Candle = {
  symbol: string;
  timeframe: string;
  open_time: string;
  close_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  quote_volume: string | null;
  source: string;
  as_of: string;
  created_at: string;
};

export type MarketOrderBook = {
  symbol: string;
  run_id: string | null;
  as_of: string | null;
  bids: [string, string][];
  asks: [string, string][];
  mid_price: string | null;
  spread_bps: string | null;
  depth_1pct_usd: string | null;
  source: string | null;
  data_policy: string;
  private_methods_allowed: boolean;
};

export type MarketEvent = {
  event_id: string;
  type: string;
  symbol: string | null;
  simulated_time: string;
  payload: Record<string, unknown>;
  source: string;
  confidence: number;
};

export type AgentRun = {
  agent_run_id: string;
  run_id: string;
  decision_id: string;
  agent_id: string;
  status: "completed" | "failed" | "replayed";
  started_at_sim_time: string;
  completed_at_sim_time: string;
};

export type AgentMessage = {
  message_id: string;
  agent_run_id: string;
  role: "system" | "observation" | "assistant" | "critic" | "risk";
  content: Record<string, unknown>;
  created_at_sim_time: string;
};

export type DecisionTrace = {
  decision: TradeIntent;
  agent_run: AgentRun;
  messages: AgentMessage[];
  risk_review: RiskReview | null;
  order: SimOrder | null;
  fill: Fill | null;
};

export type DecisionReview = {
  review_id: string;
  decision_id: string;
  run_id: string;
  horizon: string;
  realized_return: string;
  max_adverse_excursion: string;
  max_favorable_excursion: string;
  was_correct_directionally: boolean;
  error_tags: string[];
  reviewer_summary: string;
  created_at_sim_time: string;
};

export type MemoryEntry = {
  memory_id: string;
  run_id: string;
  decision_id: string | null;
  memory_type: "decision" | "failure" | "regime" | "agent" | "experiment";
  summary: string;
  content: Record<string, unknown>;
  tags: string[];
  available_at_sim_time: string;
  created_at: string;
};

export type PluginPermissions = {
  read_market_data: boolean;
  read_portfolio: boolean;
  write_market_events: boolean;
  write_features: boolean;
  write_orders: boolean;
  network_access: boolean;
  file_system_access: "none" | "sandbox" | "readonly";
  approved_directories: string[];
  provider_allowlist: string[];
  methods_allowlist: string[];
  rate_limit_per_minute: number | null;
  credential_scope: "none" | "market_data";
  cpu_time_limit_seconds: number | null;
  memory_limit_mb: number | null;
  wall_time_limit_seconds: number | null;
};

export type PluginManifest = {
  name: string;
  version: string;
  plugin_type:
    | "market_data_connector"
    | "data_import"
    | "synthetic_market"
    | "feature_calculation"
    | "event_generation"
    | "analysis_tool"
    | "report"
    | "experiment";
  description: string;
  permissions: PluginPermissions;
  inputs: string[];
  output_schema: string;
  tests: string[];
};

export type SandboxResult = {
  passed: boolean;
  violations: string[];
  warnings: string[];
};

export type PluginRegistryEntry = {
  plugin_id: string;
  manifest: PluginManifest;
  manifest_digest: string;
  sandbox_result: SandboxResult;
  status: "draft" | "validated" | "enabled" | "archived" | "rejected";
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
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
  min_order_notional: string;
  max_order_notional: string;
  max_leverage: string;
  max_drawdown: string;
  max_daily_loss: string;
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
  events: MarketEvent[];
  decisions: TradeIntent[];
  orders: SimOrder[];
  fills: Fill[];
  portfolioSummary: PortfolioSummary;
  positions: PositionView[];
  riskLimits: RiskLimits;
  latestRiskReview: RiskReview | null;
  alerts: Alert[];
};

export type RunMarketData = {
  source: DataSource;
  run: SimulationRun;
  symbols: MarketSymbolsResponse;
  candles: Candle[];
  orderBook: MarketOrderBook;
  events: MarketEvent[];
  orders: SimOrder[];
  fills: Fill[];
};

export type RunTraceData = {
  source: DataSource;
  run: SimulationRun;
  agentRuns: AgentRun[];
  messagesByAgentRunId: Record<string, AgentMessage[]>;
  traces: DecisionTrace[];
};

export type RunReviewData = {
  source: DataSource;
  run: SimulationRun;
  decisions: TradeIntent[];
  reviewsByDecisionId: Record<string, DecisionReview[]>;
  latestRiskReview: RiskReview | null;
};

export type RunReportData = {
  source: DataSource;
  run: SimulationRun;
  decisions: TradeIntent[];
  simulationReports: ReportArtifact[];
  decisionReports: ReportArtifact[];
};

export type RunMemoryData = {
  source: DataSource;
  run: SimulationRun;
  memoryEntries: MemoryEntry[];
  decisions: TradeIntent[];
  reviewsByDecisionId: Record<string, DecisionReview[]>;
};

export type SettingsPageData = {
  source: DataSource;
  health: BackendHealthState;
  symbols: MarketSymbolsResponse;
  run: SimulationRun;
  riskLimits: RiskLimits;
};

export type DatasetDetailData = {
  source: DataSource;
  dataset: DatasetRecord;
  quality: DatasetQualityReport;
  candles: Candle[];
};

export type ExperimentDetailData = {
  source: DataSource;
  experiment: ExperimentRecord;
  dataset: DatasetRecord | null;
  reports: ReportArtifact[];
};

export type ModelDetailData = {
  source: DataSource;
  model: ModelRegistryEntry;
  trainingDataset: DatasetRecord | null;
  validationDataset: DatasetRecord | null;
};

export type Metric = {
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "good" | "warn" | "danger";
};
