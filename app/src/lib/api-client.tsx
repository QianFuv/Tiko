/**
 * API client helpers for the Tiko frontend control surface.
 */

import type {
  ApiData,
  BackendHealthState,
  DataSource,
  DatasetQualityReport,
  DatasetRecord,
  ExperimentRecord,
  Fill,
  PortfolioSummary,
  PositionView,
  RiskLimits,
  RiskReview,
  RunDashboardData,
  SimAccount,
  SimOrder,
  SimulationRun,
  TradeIntent,
} from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEMO_RUN_ID = "demo-run";
const DEMO_ACCOUNT_ID = "00000000-0000-4000-8000-000000000001";
const DEMO_DECISION_ID = "00000000-0000-4000-8000-000000000101";
const DEMO_ORDER_ID = "00000000-0000-4000-8000-000000000201";
const DEMO_FILL_ID = "00000000-0000-4000-8000-000000000301";
const DEMO_REVIEW_ID = "00000000-0000-4000-8000-000000000401";
const DEMO_DATASET_ID = "00000000-0000-4000-8000-000000000901";
const DEMO_EXPERIMENT_ID = "00000000-0000-4000-8000-000000001001";
const DEMO_TIME = "2026-05-31T00:00:00Z";

/**
 * Resolve the configured backend API base URL.
 *
 * @returns Backend API base URL without a trailing slash.
 */
export function getApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(
    /\/$/,
    "",
  );
}

/**
 * Fetch backend health without making dashboard rendering depend on it.
 *
 * @returns Backend health state with unavailable status on connection failure.
 */
export async function fetchBackendHealth(): Promise<BackendHealthState> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/api/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });
    if (!response.ok) {
      return {
        status: "unavailable",
        data: null,
        error: `Backend returned HTTP ${response.status}`,
      };
    }
    return {
      status: "available",
      data: (await response.json()) as BackendHealthState["data"],
      error: null,
    };
  } catch (error) {
    return {
      status: "unavailable",
      data: null,
      error: error instanceof Error ? error.message : "Backend unavailable",
    };
  }
}

/**
 * Fetch all simulation runs.
 *
 * @returns Simulation runs from the backend or demo fallback data.
 */
export async function fetchSimulations(): Promise<ApiData<SimulationRun[]>> {
  return fetchApiData("/api/simulations", () => [buildDemoRun(DEMO_RUN_ID)]);
}

/**
 * Fetch one simulation run by ID.
 *
 * @param runId - Simulation run identifier.
 * @returns Simulation run from the backend or demo fallback data.
 */
export async function fetchSimulation(
  runId: string,
): Promise<ApiData<SimulationRun>> {
  return fetchApiData(`/api/simulations/${runId}`, () => buildDemoRun(runId));
}

/**
 * Fetch imported research datasets.
 *
 * @returns Dataset records from the backend or demo fallback data.
 */
export async function fetchDatasets(): Promise<ApiData<DatasetRecord[]>> {
  return fetchApiData("/api/datasets", buildDemoDatasets);
}

/**
 * Fetch quality reports for imported datasets.
 *
 * @param datasets - Datasets to resolve quality reports for.
 * @returns Quality reports from the backend or demo fallback data.
 */
export async function fetchDatasetQualityReports(
  datasets: DatasetRecord[],
): Promise<ApiData<DatasetQualityReport[]>> {
  if (datasets.length === 0) {
    return { data: [], source: "backend", error: null };
  }
  const results = await Promise.all(
    datasets.map((dataset) =>
      fetchApiData(`/api/datasets/${dataset.dataset_id}/quality`, () =>
        buildDemoDatasetQualityReport(dataset),
      ),
    ),
  );
  return {
    data: results.map((result) => result.data),
    source: combineDataSources(results.map((result) => result.source)),
    error: results.find((result) => result.error !== null)?.error ?? null,
  };
}

/**
 * Fetch research experiments.
 *
 * @returns Experiment records from the backend or demo fallback data.
 */
export async function fetchExperiments(): Promise<ApiData<ExperimentRecord[]>> {
  return fetchApiData("/api/experiments", buildDemoExperiments);
}

/**
 * Fetch structured trade intents, optionally filtered by run.
 *
 * @param runId - Optional simulation run identifier.
 * @returns Trade intents from the backend or demo fallback data.
 */
export async function fetchDecisions(
  runId?: string,
): Promise<ApiData<TradeIntent[]>> {
  return fetchApiData(
    "/api/decisions",
    () => buildDemoDecisions(runId ?? DEMO_RUN_ID),
    (decisions) =>
      decisions.filter(
        (decision) => runId === undefined || decision.run_id === runId,
      ),
  );
}

/**
 * Fetch simulated orders, optionally filtered by run.
 *
 * @param runId - Optional simulation run identifier.
 * @returns Simulated orders from the backend or demo fallback data.
 */
export async function fetchOrders(
  runId?: string,
): Promise<ApiData<SimOrder[]>> {
  return fetchApiData(
    "/api/orders",
    () => buildDemoOrders(runId ?? DEMO_RUN_ID),
    (orders) =>
      orders.filter((order) => runId === undefined || order.run_id === runId),
  );
}

/**
 * Fetch simulated fills, optionally filtered by run.
 *
 * @param runId - Optional simulation run identifier.
 * @returns Simulated fills from the backend or demo fallback data.
 */
export async function fetchFills(runId?: string): Promise<ApiData<Fill[]>> {
  return fetchApiData(
    "/api/fills",
    () => buildDemoFills(runId ?? DEMO_RUN_ID),
    (fills) =>
      fills.filter((fill) => runId === undefined || fill.run_id === runId),
  );
}

/**
 * Fetch simulated portfolio summary for a run.
 *
 * @param runId - Simulation run identifier.
 * @returns Portfolio summary from the backend or demo fallback data.
 */
export async function fetchPortfolioSummary(
  runId: string,
): Promise<ApiData<PortfolioSummary>> {
  return fetchApiData(`/api/portfolio/${runId}/summary`, () =>
    buildDemoPortfolioSummary(runId),
  );
}

/**
 * Fetch active risk limits for a run.
 *
 * @param runId - Simulation run identifier.
 * @returns Risk limits from the backend or demo fallback data.
 */
export async function fetchRiskLimits(
  runId: string,
): Promise<ApiData<RiskLimits>> {
  return fetchApiData(`/api/risk/${runId}/limits`, () =>
    buildDemoRiskLimits(runId),
  );
}

/**
 * Fetch the latest risk review for a run.
 *
 * @param runId - Simulation run identifier.
 * @returns Latest risk review from the backend or demo fallback data.
 */
export async function fetchLatestRiskReview(
  runId: string,
): Promise<ApiData<RiskReview | null>> {
  return fetchApiData(`/api/risk/${runId}/reviews/latest`, buildDemoRiskReview);
}

/**
 * Fetch all data needed by run-level observation pages.
 *
 * @param runId - Simulation run identifier.
 * @returns Aggregated dashboard data.
 */
export async function fetchRunDashboardData(
  runId: string,
): Promise<RunDashboardData> {
  const [
    health,
    runResult,
    decisionsResult,
    ordersResult,
    fillsResult,
    portfolioSummaryResult,
    riskLimitsResult,
    latestRiskReviewResult,
  ] = await Promise.all([
    fetchBackendHealth(),
    fetchSimulation(runId),
    fetchDecisions(runId),
    fetchOrders(runId),
    fetchFills(runId),
    fetchPortfolioSummary(runId),
    fetchRiskLimits(runId),
    fetchLatestRiskReview(runId),
  ]);
  return {
    apiBaseUrl: getApiBaseUrl(),
    source: combineDataSources([
      runResult.source,
      decisionsResult.source,
      ordersResult.source,
      fillsResult.source,
      portfolioSummaryResult.source,
      riskLimitsResult.source,
      latestRiskReviewResult.source,
    ]),
    health,
    run: runResult.data,
    decisions: decisionsResult.data,
    orders: ordersResult.data,
    fills: fillsResult.data,
    portfolioSummary: portfolioSummaryResult.data,
    positions: buildPositionsFromFills(runResult.data, fillsResult.data),
    riskLimits: riskLimitsResult.data,
    latestRiskReview: latestRiskReviewResult.data,
  };
}

/**
 * Fetch API JSON with deterministic fallback data.
 *
 * @param path - API path beginning with `/api`.
 * @param fallback - Fallback data factory.
 * @param transform - Optional transform for backend data.
 * @returns Data result with source metadata.
 */
async function fetchApiData<T>(
  path: string,
  fallback: () => T,
  transform?: (data: T) => T,
): Promise<ApiData<T>> {
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });
    if (!response.ok) {
      throw new Error(`Backend returned HTTP ${response.status}`);
    }
    const data = (await response.json()) as T;
    return {
      data: transform === undefined ? data : transform(data),
      source: "backend",
      error: null,
    };
  } catch (error) {
    return {
      data: fallback(),
      source: "demo",
      error: error instanceof Error ? error.message : "Backend unavailable",
    };
  }
}

/**
 * Derive current positions from simulated fills.
 *
 * @param run - Simulation run.
 * @param fills - Simulated fills for the run.
 * @returns Position views grouped by symbol.
 */
function buildPositionsFromFills(
  run: SimulationRun,
  fills: Fill[],
): PositionView[] {
  const quantitiesBySymbol = new Map<string, number>();
  const notionalsBySymbol = new Map<string, number>();
  let latestTime = run.current_sim_time;
  for (const fill of fills) {
    const direction = fill.side === "sell" ? -1 : 1;
    const signedQuantity = direction * parseDecimal(fill.quantity);
    const signedNotional =
      direction * parseDecimal(fill.quantity) * parseDecimal(fill.price);
    quantitiesBySymbol.set(
      fill.symbol,
      (quantitiesBySymbol.get(fill.symbol) ?? 0) + signedQuantity,
    );
    notionalsBySymbol.set(
      fill.symbol,
      (notionalsBySymbol.get(fill.symbol) ?? 0) + signedNotional,
    );
    latestTime = fill.filled_at_sim_time;
  }
  return Array.from(quantitiesBySymbol.entries())
    .filter(([, quantity]) => quantity !== 0)
    .map(([symbol, quantity]) => {
      const notional = notionalsBySymbol.get(symbol) ?? 0;
      const absoluteQuantity = Math.abs(quantity);
      const avgEntryPrice =
        absoluteQuantity > 0 ? Math.abs(notional) / absoluteQuantity : 0;
      return {
        positionId: `${run.run_id}-${symbol}`,
        accountId: run.account.account_id,
        symbol,
        side: quantity > 0 ? "long" : "short",
        quantity: absoluteQuantity.toFixed(6),
        avgEntryPrice: avgEntryPrice.toFixed(2),
        markPrice: avgEntryPrice.toFixed(2),
        notional: Math.abs(notional).toFixed(2),
        leverage: "1",
        unrealizedPnl: "0",
        realizedPnl: run.account.realized_pnl,
        liquidationPrice: null,
        updatedAtSimTime: latestTime,
      };
    });
}

/**
 * Combine several data source markers into one page-level marker.
 *
 * @param sources - Data source markers.
 * @returns Combined source marker.
 */
function combineDataSources(sources: DataSource[]): DataSource {
  return sources.every((source) => source === "backend")
    ? "backend"
    : sources.every((source) => source === "demo")
      ? "demo"
      : "mixed";
}

/**
 * Build a deterministic demo simulation run.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo simulation run.
 */
function buildDemoRun(runId: string): SimulationRun {
  return {
    run_id: runId,
    name: "BTCUSDT long-run simulation",
    status: "running",
    mode: "synthetic_market",
    account: buildDemoAccount(),
    symbols: ["BTCUSDT", "ETHUSDT"],
    start_sim_time: "2026-05-30T00:00:00Z",
    current_sim_time: DEMO_TIME,
    end_sim_time: null,
    speed_multiplier: "10",
    config: {
      decision_interval: "1h",
      safety_mode: "simulation_only",
    },
    created_at: "2026-05-30T00:00:00Z",
  };
}

/**
 * Build deterministic demo dataset records.
 *
 * @returns Demo dataset records.
 */
function buildDemoDatasets(): DatasetRecord[] {
  return [
    {
      dataset_id: DEMO_DATASET_ID,
      name: "BTCUSDT hourly research candles",
      source: "csv",
      source_uri: "demo://datasets/btcusdt-hourly.csv",
      symbols: ["BTCUSDT"],
      timeframes: ["1h"],
      candle_count: 720,
      status: "validated",
      start_time: "2026-05-01T00:00:00Z",
      end_time: "2026-05-31T00:00:00Z",
      created_at: "2026-05-31T00:00:00Z",
    },
  ];
}

/**
 * Build deterministic demo dataset quality.
 *
 * @param dataset - Dataset associated with the quality report.
 * @returns Demo dataset quality report.
 */
function buildDemoDatasetQualityReport(
  dataset: DatasetRecord,
): DatasetQualityReport {
  return {
    dataset_id: dataset.dataset_id,
    total_records: dataset.candle_count,
    error_count: dataset.status === "invalid" ? 1 : 0,
    warning_count: 0,
    has_errors: dataset.status === "invalid",
    issues: [],
  };
}

/**
 * Build deterministic demo experiment records.
 *
 * @returns Demo experiment records.
 */
function buildDemoExperiments(): ExperimentRecord[] {
  return [
    {
      experiment_id: DEMO_EXPERIMENT_ID,
      name: "Momentum walk-forward baseline",
      kind: "walk_forward",
      hypothesis: "Momentum remains positive across validation splits.",
      dataset_id: DEMO_DATASET_ID,
      model_id: null,
      parameters: {
        splits: 3,
        lookback_hours: 24,
        max_target_weight: "0.12",
      },
      status: "queued",
      metrics: {
        queued: true,
      },
      created_at: "2026-05-31T00:00:00Z",
      queued_at: DEMO_TIME,
      completed_at: null,
    },
  ];
}

/**
 * Build a deterministic demo simulated account.
 *
 * @returns Demo account.
 */
function buildDemoAccount(): SimAccount {
  return {
    account_id: DEMO_ACCOUNT_ID,
    name: "Research account",
    base_currency: "USDT",
    initial_equity: "100000",
    cash_balance: "87964.50",
    total_equity: "101842.25",
    realized_pnl: "1268.40",
    unrealized_pnl: "573.85",
    max_drawdown: "0.031",
    status: "active",
  };
}

/**
 * Build deterministic demo decisions.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo trade intents.
 */
function buildDemoDecisions(runId: string): TradeIntent[] {
  return [
    {
      decision_id: DEMO_DECISION_ID,
      run_id: runId,
      agent_id: "rule_based_trader",
      symbol: "BTCUSDT",
      market_type: "synthetic",
      action: "open_long",
      target_weight: "0.12",
      target_notional: "12000",
      max_leverage: "1",
      confidence: 0.74,
      expected_holding_period: "4h",
      thesis:
        "Momentum remains positive while data quality and risk gates hold.",
      evidence: [
        {
          source: "observation",
          signal: "last_close_above_open",
          confidence: 0.74,
        },
      ],
      invalidation_conditions: [
        "Confidence drops below minimum.",
        "Data quality falls below policy.",
      ],
      data_quality_score: 0.98,
      created_at_sim_time: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo orders.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo simulated orders.
 */
function buildDemoOrders(runId: string): SimOrder[] {
  return [
    {
      order_id: DEMO_ORDER_ID,
      run_id: runId,
      account_id: DEMO_ACCOUNT_ID,
      decision_id: DEMO_DECISION_ID,
      symbol: "BTCUSDT",
      side: "buy",
      order_type: "market",
      quantity: "0.176500",
      limit_price: null,
      status: "filled",
      submitted_at_sim_time: DEMO_TIME,
      updated_at_sim_time: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo fills.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo simulated fills.
 */
function buildDemoFills(runId: string): Fill[] {
  return [
    {
      fill_id: DEMO_FILL_ID,
      order_id: DEMO_ORDER_ID,
      run_id: runId,
      symbol: "BTCUSDT",
      side: "buy",
      quantity: "0.176500",
      price: "68000.00",
      fee: "6.00",
      slippage_bps: "3",
      filled_at_sim_time: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo portfolio summary.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo portfolio summary.
 */
function buildDemoPortfolioSummary(runId: string): PortfolioSummary {
  const account = buildDemoAccount();
  return {
    run_id: runId,
    base_currency: account.base_currency,
    cash_balance: account.cash_balance,
    total_equity: account.total_equity,
    realized_pnl: account.realized_pnl,
    unrealized_pnl: account.unrealized_pnl,
    max_drawdown: account.max_drawdown,
    gross_exposure: "12002.00",
  };
}

/**
 * Build deterministic demo risk limits.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo risk limits.
 */
function buildDemoRiskLimits(runId: string): RiskLimits {
  return {
    run_id: runId,
    minimum_confidence: 0.6,
    minimum_data_quality_score: 0.8,
    max_target_weight: "0.25",
    max_order_notional: "25000",
    live_trading_allowed: false,
  };
}

/**
 * Build deterministic demo risk review.
 *
 * @returns Demo risk review.
 */
function buildDemoRiskReview(): RiskReview {
  return {
    review_id: DEMO_REVIEW_ID,
    decision_id: DEMO_DECISION_ID,
    status: "approved",
    original_target_weight: "0.12",
    approved_target_weight: "0.12",
    max_order_notional: "25000",
    reasons: ["Confidence, data quality, and notional limits passed."],
    triggered_rules: [
      "minimum_confidence",
      "data_quality",
      "max_order_notional",
    ],
    created_at_sim_time: DEMO_TIME,
  };
}

/**
 * Parse a decimal-like string for display-only calculations.
 *
 * @param value - Decimal string.
 * @returns Parsed number or zero.
 */
function parseDecimal(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
