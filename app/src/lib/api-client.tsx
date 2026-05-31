/**
 * API client helpers for the Tiko frontend control surface.
 */

import type {
  AgentMessage,
  AgentRun,
  ApiData,
  BackendHealthState,
  Candle,
  DataSource,
  DatasetDetailData,
  DatasetQualityReport,
  DatasetRecord,
  DecisionReview,
  DecisionTrace,
  ExperimentDetailData,
  ExperimentRecord,
  Fill,
  MarketEvent,
  MarketOrderBook,
  MarketSymbolsResponse,
  MemoryEntry,
  ModelDetailData,
  ModelRegistryEntry,
  PortfolioSummary,
  PositionView,
  PluginRegistryEntry,
  ReportArtifact,
  RiskLimits,
  RiskReview,
  RunDashboardData,
  RunMarketData,
  RunMemoryData,
  RunReportData,
  RunReviewData,
  RunTraceData,
  SettingsPageData,
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
const DEMO_AGENT_RUN_ID = "00000000-0000-4000-8000-000000000501";
const DEMO_OBSERVATION_MESSAGE_ID = "00000000-0000-4000-8000-000000000601";
const DEMO_ASSISTANT_MESSAGE_ID = "00000000-0000-4000-8000-000000000602";
const DEMO_DECISION_REVIEW_ID = "00000000-0000-4000-8000-000000000701";
const DEMO_MEMORY_ID = "00000000-0000-4000-8000-000000000801";
const DEMO_DATASET_ID = "00000000-0000-4000-8000-000000000901";
const DEMO_EXPERIMENT_ID = "00000000-0000-4000-8000-000000001001";
const DEMO_MODEL_ID = "00000000-0000-4000-8000-000000001101";
const DEMO_REPORT_ID = "00000000-0000-4000-8000-000000001201";
const DEMO_PLUGIN_ID = "00000000-0000-4000-8000-000000001301";
const DEMO_EVENT_ID = "00000000-0000-4000-8000-000000001401";
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
 * Fetch one imported research dataset.
 *
 * @param datasetId - Dataset identifier.
 * @returns Dataset record from the backend or demo fallback data.
 */
export async function fetchDataset(
  datasetId: string,
): Promise<ApiData<DatasetRecord>> {
  return fetchApiData(`/api/datasets/${datasetId}`, () =>
    buildDemoDataset(datasetId),
  );
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
 * Fetch a quality report for one dataset.
 *
 * @param dataset - Dataset associated with the report.
 * @returns Dataset quality report from the backend or demo fallback data.
 */
export async function fetchDatasetQualityReport(
  dataset: DatasetRecord,
): Promise<ApiData<DatasetQualityReport>> {
  return fetchApiData(`/api/datasets/${dataset.dataset_id}/quality`, () =>
    buildDemoDatasetQualityReport(dataset),
  );
}

/**
 * Fetch a bounded candle sample for one dataset.
 *
 * @param dataset - Dataset associated with the candle sample.
 * @returns Dataset candles from the backend or demo fallback data.
 */
export async function fetchDatasetCandles(
  dataset: DatasetRecord,
): Promise<ApiData<Candle[]>> {
  return fetchApiData(`/api/datasets/${dataset.dataset_id}/candles`, () =>
    buildDemoCandles(),
  );
}

/**
 * Fetch all detail page data for one dataset.
 *
 * @param datasetId - Dataset identifier.
 * @returns Dataset detail data.
 */
export async function fetchDatasetDetailData(
  datasetId: string,
): Promise<DatasetDetailData> {
  const datasetResult = await fetchDataset(datasetId);
  const [qualityResult, candlesResult] = await Promise.all([
    fetchDatasetQualityReport(datasetResult.data),
    fetchDatasetCandles(datasetResult.data),
  ]);
  return {
    source: combineDataSources([
      datasetResult.source,
      qualityResult.source,
      candlesResult.source,
    ]),
    dataset: datasetResult.data,
    quality: qualityResult.data,
    candles: candlesResult.data,
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
 * Fetch one research experiment.
 *
 * @param experimentId - Experiment identifier.
 * @returns Experiment record from the backend or demo fallback data.
 */
export async function fetchExperiment(
  experimentId: string,
): Promise<ApiData<ExperimentRecord>> {
  return fetchApiData(`/api/experiments/${experimentId}`, () =>
    buildDemoExperiment(experimentId),
  );
}

/**
 * Fetch experiment reports for one experiment.
 *
 * @param experimentId - Experiment identifier.
 * @returns Experiment reports from the backend or demo fallback data.
 */
export async function fetchExperimentReports(
  experimentId: string,
): Promise<ApiData<ReportArtifact[]>> {
  return fetchApiData(`/api/reports/experiments/${experimentId}`, () =>
    buildDemoExperimentReports(experimentId),
  );
}

/**
 * Fetch all detail page data for one experiment.
 *
 * @param experimentId - Experiment identifier.
 * @returns Experiment detail data.
 */
export async function fetchExperimentDetailData(
  experimentId: string,
): Promise<ExperimentDetailData> {
  const experimentResult = await fetchExperiment(experimentId);
  const [datasetResult, reportsResult] = await Promise.all([
    fetchDataset(experimentResult.data.dataset_id),
    fetchExperimentReports(experimentResult.data.experiment_id),
  ]);
  return {
    source: combineDataSources([
      experimentResult.source,
      datasetResult.source,
      reportsResult.source,
    ]),
    experiment: experimentResult.data,
    dataset: datasetResult.data,
    reports: reportsResult.data,
  };
}

/**
 * Fetch model registry entries.
 *
 * @returns Model registry entries from the backend or demo fallback data.
 */
export async function fetchModels(): Promise<ApiData<ModelRegistryEntry[]>> {
  return fetchApiData("/api/models", buildDemoModels);
}

/**
 * Fetch one model registry entry.
 *
 * @param modelId - Model identifier.
 * @returns Model registry entry from the backend or demo fallback data.
 */
export async function fetchModel(
  modelId: string,
): Promise<ApiData<ModelRegistryEntry>> {
  return fetchApiData(`/api/models/${modelId}`, () => buildDemoModel(modelId));
}

/**
 * Fetch all detail page data for one model.
 *
 * @param modelId - Model identifier.
 * @returns Model detail data.
 */
export async function fetchModelDetailData(
  modelId: string,
): Promise<ModelDetailData> {
  const modelResult = await fetchModel(modelId);
  const [trainingDatasetResult, validationDatasetResult] = await Promise.all([
    fetchDataset(modelResult.data.training_dataset_id),
    fetchDataset(modelResult.data.validation_dataset_id),
  ]);
  return {
    source: combineDataSources([
      modelResult.source,
      trainingDatasetResult.source,
      validationDatasetResult.source,
    ]),
    model: modelResult.data,
    trainingDataset: trainingDatasetResult.data,
    validationDataset: validationDatasetResult.data,
  };
}

/**
 * Fetch report artifacts from scoped report endpoints.
 *
 * @returns Aggregated reports from the backend or demo fallback data.
 */
export async function fetchReports(): Promise<ApiData<ReportArtifact[]>> {
  const [simulationsResult, decisionsResult, experimentsResult] =
    await Promise.all([
      fetchSimulations(),
      fetchDecisions(),
      fetchExperiments(),
    ]);
  const reportRequests = [
    ...simulationsResult.data.map((run) =>
      fetchApiData(
        `/api/reports/simulations/${run.run_id}`,
        () => [] as ReportArtifact[],
      ),
    ),
    ...decisionsResult.data.map((decision) =>
      fetchApiData(
        `/api/reports/decisions/${decision.decision_id}`,
        () => [] as ReportArtifact[],
      ),
    ),
    ...experimentsResult.data.map((experiment) =>
      fetchApiData(
        `/api/reports/experiments/${experiment.experiment_id}`,
        () => [] as ReportArtifact[],
      ),
    ),
  ];
  const reportResults: ApiData<ReportArtifact[]>[] =
    reportRequests.length === 0 ? [] : await Promise.all(reportRequests);
  if (
    simulationsResult.source === "demo" &&
    decisionsResult.source === "demo" &&
    experimentsResult.source === "demo"
  ) {
    return {
      data: buildDemoReports(),
      source: "demo",
      error:
        simulationsResult.error ??
        decisionsResult.error ??
        experimentsResult.error,
    };
  }
  return {
    data: reportResults.flatMap((result) => result.data),
    source: combineDataSources([
      simulationsResult.source,
      decisionsResult.source,
      experimentsResult.source,
      ...reportResults.map((result) => result.source),
    ]),
    error:
      reportResults.find((result) => result.error !== null)?.error ??
      simulationsResult.error ??
      decisionsResult.error ??
      experimentsResult.error,
  };
}

/**
 * Fetch market symbols and read-only policy metadata.
 *
 * @returns Market symbols from the backend or demo fallback data.
 */
export async function fetchMarketSymbols(): Promise<
  ApiData<MarketSymbolsResponse>
> {
  return fetchApiData("/api/market/symbols", buildDemoMarketSymbols);
}

/**
 * Fetch run candles.
 *
 * @param runId - Simulation run identifier.
 * @returns Run candles from the backend or demo fallback data.
 */
export async function fetchMarketCandles(
  runId: string,
): Promise<ApiData<Candle[]>> {
  return fetchApiData(`/api/market/candles?run_id=${runId}`, () =>
    buildDemoCandles(),
  );
}

/**
 * Fetch read-only order book policy data for a symbol.
 *
 * @param symbol - Market symbol.
 * @returns Order book data from the backend or demo fallback data.
 */
export async function fetchMarketOrderBook(
  symbol: string,
): Promise<ApiData<MarketOrderBook>> {
  return fetchApiData(
    `/api/market/orderbook?symbol=${encodeURIComponent(symbol)}`,
    () => buildDemoOrderBook(symbol),
  );
}

/**
 * Fetch run market events.
 *
 * @param runId - Simulation run identifier.
 * @returns Run events from the backend or demo fallback data.
 */
export async function fetchMarketEvents(
  runId: string,
): Promise<ApiData<MarketEvent[]>> {
  return fetchApiData(
    `/api/simulations/${runId}/events`,
    buildDemoMarketEvents,
  );
}

/**
 * Fetch all market page data for a simulation run.
 *
 * @param runId - Simulation run identifier.
 * @returns Aggregated run market data.
 */
export async function fetchRunMarketData(
  runId: string,
): Promise<RunMarketData> {
  const runResult = await fetchSimulation(runId);
  const primarySymbol = runResult.data.symbols[0] ?? "BTCUSDT";
  const [symbolsResult, candlesResult, orderBookResult, eventsResult] =
    await Promise.all([
      fetchMarketSymbols(),
      fetchMarketCandles(runId),
      fetchMarketOrderBook(primarySymbol),
      fetchMarketEvents(runId),
    ]);
  return {
    source: combineDataSources([
      runResult.source,
      symbolsResult.source,
      candlesResult.source,
      orderBookResult.source,
      eventsResult.source,
    ]),
    run: runResult.data,
    symbols: symbolsResult.data,
    candles: candlesResult.data,
    orderBook: orderBookResult.data,
    events: eventsResult.data,
  };
}

/**
 * Fetch memory entries for a simulation run.
 *
 * @param runId - Simulation run identifier.
 * @returns Memory entries from the backend or demo fallback data.
 */
export async function fetchMemoryEntries(
  runId: string,
): Promise<ApiData<MemoryEntry[]>> {
  return fetchApiData(`/api/simulations/${runId}/memory`, () =>
    buildDemoMemoryEntries(runId),
  );
}

/**
 * Fetch run memory and review context.
 *
 * @param runId - Simulation run identifier.
 * @returns Aggregated run memory data.
 */
export async function fetchRunMemoryData(
  runId: string,
): Promise<RunMemoryData> {
  const [runResult, memoryResult, decisionsResult] = await Promise.all([
    fetchSimulation(runId),
    fetchMemoryEntries(runId),
    fetchDecisions(runId),
  ]);
  const reviewResults = await Promise.all(
    decisionsResult.data.map((decision) => fetchDecisionReviews(decision)),
  );
  return {
    source: combineDataSources([
      runResult.source,
      memoryResult.source,
      decisionsResult.source,
      ...reviewResults.map((result) => result.source),
    ]),
    run: runResult.data,
    memoryEntries: memoryResult.data,
    decisions: decisionsResult.data,
    reviewsByDecisionId: buildReviewMap(decisionsResult.data, reviewResults),
  };
}

/**
 * Fetch plugin registry entries.
 *
 * @returns Plugin registry entries from the backend or demo fallback data.
 */
export async function fetchPlugins(): Promise<ApiData<PluginRegistryEntry[]>> {
  return fetchApiData("/api/plugins", buildDemoPlugins);
}

/**
 * Fetch settings and safety overview data.
 *
 * @returns Aggregated settings page data.
 */
export async function fetchSettingsData(): Promise<SettingsPageData> {
  const [health, simulationsResult, symbolsResult] = await Promise.all([
    fetchBackendHealth(),
    fetchSimulations(),
    fetchMarketSymbols(),
  ]);
  const run = simulationsResult.data[0] ?? buildDemoRun(DEMO_RUN_ID);
  const riskLimitsResult = await fetchRiskLimits(run.run_id);
  return {
    source: combineDataSources([
      simulationsResult.source,
      symbolsResult.source,
      riskLimitsResult.source,
    ]),
    health,
    symbols: symbolsResult.data,
    run,
    riskLimits: riskLimitsResult.data,
  };
}

/**
 * Fetch agent runtime traces for a simulation run.
 *
 * @param runId - Simulation run identifier.
 * @returns Aggregated agent run, message, and decision trace data.
 */
export async function fetchRunTraceData(runId: string): Promise<RunTraceData> {
  const [runResult, decisionsResult, agentRunsResult] = await Promise.all([
    fetchSimulation(runId),
    fetchDecisions(runId),
    fetchAgentRuns(runId),
  ]);
  const [messageResults, traceResults] = await Promise.all([
    Promise.all(
      agentRunsResult.data.map((agentRun) =>
        fetchAgentMessages(agentRun.agent_run_id),
      ),
    ),
    Promise.all(
      decisionsResult.data.map((decision) => fetchDecisionTrace(decision)),
    ),
  ]);
  return {
    source: combineDataSources([
      runResult.source,
      decisionsResult.source,
      agentRunsResult.source,
      ...messageResults.map((result) => result.source),
      ...traceResults.map((result) => result.source),
    ]),
    run: runResult.data,
    agentRuns: agentRunsResult.data,
    messagesByAgentRunId: buildMessageMap(agentRunsResult.data, messageResults),
    traces: traceResults.map((result) => result.data),
  };
}

/**
 * Fetch posterior decision reviews for a simulation run.
 *
 * @param runId - Simulation run identifier.
 * @returns Aggregated decision review data.
 */
export async function fetchRunReviewData(
  runId: string,
): Promise<RunReviewData> {
  const [runResult, decisionsResult, latestRiskReviewResult] =
    await Promise.all([
      fetchSimulation(runId),
      fetchDecisions(runId),
      fetchLatestRiskReview(runId),
    ]);
  const reviewResults = await Promise.all(
    decisionsResult.data.map((decision) => fetchDecisionReviews(decision)),
  );
  return {
    source: combineDataSources([
      runResult.source,
      decisionsResult.source,
      latestRiskReviewResult.source,
      ...reviewResults.map((result) => result.source),
    ]),
    run: runResult.data,
    decisions: decisionsResult.data,
    reviewsByDecisionId: buildReviewMap(decisionsResult.data, reviewResults),
    latestRiskReview: latestRiskReviewResult.data,
  };
}

/**
 * Fetch run-scoped simulation and decision reports.
 *
 * @param runId - Simulation run identifier.
 * @returns Aggregated run report data.
 */
export async function fetchRunReportData(
  runId: string,
): Promise<RunReportData> {
  const [runResult, decisionsResult, simulationReportsResult] =
    await Promise.all([
      fetchSimulation(runId),
      fetchDecisions(runId),
      fetchSimulationReports(runId),
    ]);
  const decisionReportResults = await Promise.all(
    decisionsResult.data.map((decision) =>
      fetchDecisionReports(decision.decision_id, runId),
    ),
  );
  return {
    source: combineDataSources([
      runResult.source,
      decisionsResult.source,
      simulationReportsResult.source,
      ...decisionReportResults.map((result) => result.source),
    ]),
    run: runResult.data,
    simulationReports: simulationReportsResult.data,
    decisionReports: decisionReportResults.flatMap((result) => result.data),
  };
}

/**
 * Fetch agent runtime runs, optionally filtered by simulation run.
 *
 * @param runId - Optional simulation run identifier.
 * @returns Agent runtime runs from the backend or demo fallback data.
 */
export async function fetchAgentRuns(
  runId?: string,
): Promise<ApiData<AgentRun[]>> {
  return fetchApiData(
    "/api/agents/runs",
    () => buildDemoAgentRuns(runId ?? DEMO_RUN_ID),
    (agentRuns) =>
      agentRuns.filter(
        (agentRun) => runId === undefined || agentRun.run_id === runId,
      ),
  );
}

/**
 * Fetch trace messages for one agent run.
 *
 * @param agentRunId - Agent run identifier.
 * @returns Agent messages from the backend or demo fallback data.
 */
export async function fetchAgentMessages(
  agentRunId: string,
): Promise<ApiData<AgentMessage[]>> {
  return fetchApiData(`/api/agents/runs/${agentRunId}/messages`, () =>
    buildDemoAgentMessages(agentRunId),
  );
}

/**
 * Fetch joined trace artifacts for one decision.
 *
 * @param decision - Decision used for the endpoint and fallback payload.
 * @returns Decision trace from the backend or demo fallback data.
 */
export async function fetchDecisionTrace(
  decision: TradeIntent,
): Promise<ApiData<DecisionTrace>> {
  return fetchApiData(`/api/decisions/${decision.decision_id}/trace`, () =>
    buildDemoDecisionTrace(decision),
  );
}

/**
 * Fetch posterior reviews for one decision.
 *
 * @param decision - Decision used for the endpoint and fallback payload.
 * @returns Decision reviews from the backend or demo fallback data.
 */
export async function fetchDecisionReviews(
  decision: TradeIntent,
): Promise<ApiData<DecisionReview[]>> {
  return fetchApiData(`/api/decisions/${decision.decision_id}/review`, () =>
    buildDemoDecisionReviews(decision),
  );
}

/**
 * Fetch simulation reports for one run.
 *
 * @param runId - Simulation run identifier.
 * @returns Simulation reports from the backend or demo fallback data.
 */
export async function fetchSimulationReports(
  runId: string,
): Promise<ApiData<ReportArtifact[]>> {
  return fetchApiData(`/api/reports/simulations/${runId}`, () =>
    buildDemoReports(runId).filter(
      (report) => report.report_type === "simulation",
    ),
  );
}

/**
 * Fetch decision reports for one decision.
 *
 * @param decisionId - Decision identifier.
 * @param runId - Optional simulation run identifier for fallback data.
 * @returns Decision reports from the backend or demo fallback data.
 */
export async function fetchDecisionReports(
  decisionId: string,
  runId = DEMO_RUN_ID,
): Promise<ApiData<ReportArtifact[]>> {
  return fetchApiData(`/api/reports/decisions/${decisionId}`, () =>
    buildDemoDecisionReports(decisionId, runId),
  );
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
 * Build message lookup by agent run identifier.
 *
 * @param agentRuns - Agent runs used for map keys.
 * @param results - Message request results in agent run order.
 * @returns Messages keyed by agent run identifier.
 */
function buildMessageMap(
  agentRuns: AgentRun[],
  results: ApiData<AgentMessage[]>[],
): Record<string, AgentMessage[]> {
  return Object.fromEntries(
    agentRuns.map((agentRun, index) => [
      agentRun.agent_run_id,
      results[index]?.data ?? [],
    ]),
  );
}

/**
 * Build review lookup by decision identifier.
 *
 * @param decisions - Decisions used for map keys.
 * @param results - Review request results in decision order.
 * @returns Reviews keyed by decision identifier.
 */
function buildReviewMap(
  decisions: TradeIntent[],
  results: ApiData<DecisionReview[]>[],
): Record<string, DecisionReview[]> {
  return Object.fromEntries(
    decisions.map((decision, index) => [
      decision.decision_id,
      results[index]?.data ?? [],
    ]),
  );
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
 * Build one deterministic demo dataset record.
 *
 * @param datasetId - Dataset identifier.
 * @returns Demo dataset record.
 */
function buildDemoDataset(datasetId: string): DatasetRecord {
  return {
    ...buildDemoDatasets()[0],
    dataset_id: datasetId,
  };
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
 * Build one deterministic demo experiment record.
 *
 * @param experimentId - Experiment identifier.
 * @returns Demo experiment record.
 */
function buildDemoExperiment(experimentId: string): ExperimentRecord {
  return {
    ...buildDemoExperiments()[0],
    experiment_id: experimentId,
  };
}

/**
 * Build deterministic demo model registry entries.
 *
 * @returns Demo model registry entries.
 */
function buildDemoModels(): ModelRegistryEntry[] {
  return [
    {
      model_id: DEMO_MODEL_ID,
      name: "rule-based momentum baseline",
      version: "0.1.0",
      model_type: "rule",
      algorithm: "deterministic_momentum",
      training_dataset_id: DEMO_DATASET_ID,
      validation_dataset_id: DEMO_DATASET_ID,
      metrics: {
        simulated_reward: "0.12",
        max_drawdown: "0.031",
      },
      artifact_uri: "demo://models/rule-based-momentum",
      status: "paper_enabled",
      created_at: DEMO_TIME,
    },
  ];
}

/**
 * Build one deterministic demo model registry entry.
 *
 * @param modelId - Model identifier.
 * @returns Demo model registry entry.
 */
function buildDemoModel(modelId: string): ModelRegistryEntry {
  return {
    ...buildDemoModels()[0],
    model_id: modelId,
  };
}

/**
 * Build deterministic demo report artifacts.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo report artifacts.
 */
function buildDemoReports(runId = DEMO_RUN_ID): ReportArtifact[] {
  return [
    {
      report_id: DEMO_REPORT_ID,
      run_id: runId,
      report_type: "simulation",
      title: "BTCUSDT long-run simulation report",
      summary:
        "Demo report covering decisions, orders, fills, and risk checks.",
      sections: {
        activity: {
          decisions: 1,
          orders: 1,
          fills: 1,
        },
        safety: {
          live_trading_allowed: false,
        },
      },
      created_at_sim_time: DEMO_TIME,
      created_at: DEMO_TIME,
    },
    ...buildDemoDecisionReports(DEMO_DECISION_ID, runId),
  ];
}

/**
 * Build deterministic demo market symbol metadata.
 *
 * @returns Demo market symbol metadata.
 */
function buildDemoMarketSymbols(): MarketSymbolsResponse {
  return {
    symbols: ["BTCUSDT", "ETHUSDT"],
    data_policy: "read_only_public_market_data",
    private_methods_allowed: false,
  };
}

/**
 * Build deterministic demo candles.
 *
 * @returns Demo candles.
 */
function buildDemoCandles(): Candle[] {
  return [
    {
      symbol: "BTCUSDT",
      timeframe: "1h",
      open_time: "2026-05-30T23:00:00Z",
      close_time: DEMO_TIME,
      open: "67620.00",
      high: "68150.00",
      low: "67440.00",
      close: "68000.00",
      volume: "1240.50",
      quote_volume: "84290000.00",
      source: "demo",
      as_of: DEMO_TIME,
      created_at: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo order book data.
 *
 * @param symbol - Market symbol.
 * @returns Demo order book data.
 */
function buildDemoOrderBook(symbol: string): MarketOrderBook {
  return {
    symbol,
    run_id: null,
    as_of: DEMO_TIME,
    bids: [
      ["67990.00", "0.84"],
      ["67975.00", "1.12"],
    ],
    asks: [
      ["68010.00", "0.76"],
      ["68025.00", "1.40"],
    ],
    mid_price: "68000.00",
    spread_bps: "2.94",
    depth_1pct_usd: "280000.00",
    source: "demo",
    data_policy: "read_only_demo_orderbook_snapshot",
    private_methods_allowed: false,
  };
}

/**
 * Build deterministic demo market events.
 *
 * @returns Demo market events.
 */
function buildDemoMarketEvents(): MarketEvent[] {
  return [
    {
      event_id: DEMO_EVENT_ID,
      type: "candle_closed",
      symbol: "BTCUSDT",
      simulated_time: DEMO_TIME,
      payload: {
        close: "68000.00",
        source: "demo",
      },
      source: "synthetic",
      confidence: 1,
    },
  ];
}

/**
 * Build deterministic demo memory entries.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo memory entries.
 */
function buildDemoMemoryEntries(runId: string): MemoryEntry[] {
  return [
    {
      memory_id: DEMO_MEMORY_ID,
      run_id: runId,
      decision_id: DEMO_DECISION_ID,
      memory_type: "decision",
      summary: "Momentum decision remained directionally correct.",
      content: {
        realized_return: "0.018",
        review_horizon: "1h",
      },
      tags: ["posterior_review", "momentum"],
      available_at_sim_time: DEMO_TIME,
      created_at: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo plugin registry entries.
 *
 * @returns Demo plugin registry entries.
 */
function buildDemoPlugins(): PluginRegistryEntry[] {
  return [
    {
      plugin_id: DEMO_PLUGIN_ID,
      manifest: {
        name: "readonly-ccxt-market-data",
        version: "0.1.0",
        plugin_type: "market_data_connector",
        description: "Demo read-only public market data connector manifest.",
        permissions: {
          read_market_data: true,
          read_portfolio: false,
          write_market_events: false,
          write_features: false,
          write_orders: false,
          network_access: true,
          file_system_access: "sandbox",
          provider_allowlist: ["binance"],
        },
        inputs: ["symbol", "timeframe"],
        output_schema: "Candle[]",
        tests: ["public methods only"],
      },
      sandbox_result: {
        passed: true,
        violations: [],
        warnings: [],
      },
      status: "validated",
      created_at: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo decision report artifacts.
 *
 * @param decisionId - Decision identifier.
 * @param runId - Simulation run identifier.
 * @returns Demo decision report artifacts.
 */
function buildDemoDecisionReports(
  decisionId: string,
  runId = DEMO_RUN_ID,
): ReportArtifact[] {
  return [
    {
      report_id: `${DEMO_REPORT_ID.slice(0, -3)}202`,
      run_id: runId,
      report_type: "decision",
      title: "BTCUSDT momentum decision review",
      summary:
        "Demo report connecting the structured intent to trace, risk, order, and fill artifacts.",
      sections: {
        decision: {
          decision_id: decisionId,
          action: "open_long",
          confidence: 0.74,
        },
        outcome: {
          realized_return: "0.018",
          max_adverse_excursion: "-0.006",
        },
      },
      created_at_sim_time: DEMO_TIME,
      created_at: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo experiment report artifacts.
 *
 * @param experimentId - Experiment identifier.
 * @returns Demo experiment report artifacts.
 */
function buildDemoExperimentReports(experimentId: string): ReportArtifact[] {
  return [
    {
      report_id: `${DEMO_REPORT_ID.slice(0, -3)}302`,
      run_id: experimentId,
      report_type: "experiment",
      title: "Momentum walk-forward experiment report",
      summary:
        "Demo report summarizing queued walk-forward parameters and validation metrics.",
      sections: {
        experiment: {
          experiment_id: experimentId,
          kind: "walk_forward",
        },
        metrics: {
          simulated_reward: "0.12",
          max_drawdown: "0.031",
        },
      },
      created_at_sim_time: DEMO_TIME,
      created_at: DEMO_TIME,
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
 * Build deterministic demo agent run records.
 *
 * @param runId - Simulation run identifier.
 * @returns Demo agent run records.
 */
function buildDemoAgentRuns(runId: string): AgentRun[] {
  return [
    {
      agent_run_id: DEMO_AGENT_RUN_ID,
      run_id: runId,
      decision_id: DEMO_DECISION_ID,
      agent_id: "rule_based_trader",
      status: "completed",
      started_at_sim_time: DEMO_TIME,
      completed_at_sim_time: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo agent messages.
 *
 * @param agentRunId - Agent run identifier.
 * @returns Demo agent messages.
 */
function buildDemoAgentMessages(agentRunId: string): AgentMessage[] {
  return [
    {
      message_id: DEMO_OBSERVATION_MESSAGE_ID,
      agent_run_id: agentRunId,
      role: "observation",
      content: {
        symbol: "BTCUSDT",
        close_above_open: true,
        data_quality_score: 0.98,
      },
      created_at_sim_time: DEMO_TIME,
    },
    {
      message_id: DEMO_ASSISTANT_MESSAGE_ID,
      agent_run_id: agentRunId,
      role: "assistant",
      content: {
        action: "open_long",
        thesis:
          "Momentum remains positive while confidence and data quality satisfy policy gates.",
      },
      created_at_sim_time: DEMO_TIME,
    },
  ];
}

/**
 * Build deterministic demo joined decision trace data.
 *
 * @param decision - Decision associated with the trace.
 * @returns Demo decision trace data.
 */
function buildDemoDecisionTrace(decision: TradeIntent): DecisionTrace {
  const agentRun = buildDemoAgentRuns(decision.run_id)[0];
  return {
    decision,
    agent_run: {
      ...agentRun,
      decision_id: decision.decision_id,
      agent_id: decision.agent_id,
    },
    messages: buildDemoAgentMessages(agentRun.agent_run_id),
    risk_review: {
      ...buildDemoRiskReview(),
      decision_id: decision.decision_id,
    },
    order: {
      ...buildDemoOrders(decision.run_id)[0],
      decision_id: decision.decision_id,
      symbol: decision.symbol,
    },
    fill: {
      ...buildDemoFills(decision.run_id)[0],
      symbol: decision.symbol,
    },
  };
}

/**
 * Build deterministic demo posterior decision reviews.
 *
 * @param decision - Decision associated with the review.
 * @returns Demo decision reviews.
 */
function buildDemoDecisionReviews(decision: TradeIntent): DecisionReview[] {
  return [
    {
      review_id: DEMO_DECISION_REVIEW_ID,
      decision_id: decision.decision_id,
      run_id: decision.run_id,
      horizon: "1h",
      realized_return: "0.018",
      max_adverse_excursion: "-0.006",
      max_favorable_excursion: "0.026",
      was_correct_directionally: true,
      error_tags: [],
      reviewer_summary:
        "Decision remained directionally correct after the configured review horizon.",
      created_at_sim_time: DEMO_TIME,
    },
  ];
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
