import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunDashboardData, getApiBaseUrl } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  shortId,
} from "@/lib/format";
import type {
  Alert,
  AlertCategory,
  AlertSeverity,
  AlertStatus,
  Metric,
  RiskLimits,
} from "@/lib/types";

const ALERT_CATEGORIES: AlertCategory[] = [
  "pnl",
  "drawdown",
  "agent_timeout",
  "data_quality",
  "order_anomaly",
  "runtime_stuck",
  "worker_health",
  "risk_circuit_breaker",
  "model_degradation",
];
const ALERT_SEVERITIES: AlertSeverity[] = ["info", "warning", "critical"];
const ALERT_STATUS_ACTIONS: AlertStatus[] = ["acknowledged", "resolved"];

/**
 * Render risk limits and latest risk review for a run.
 *
 * @param props - Dynamic route props.
 * @returns Risk page.
 */
export default async function RiskPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunDashboardData(runId);
  const review = data.latestRiskReview;
  const metrics: Metric[] = [
    {
      label: "Min confidence",
      value: formatPercent(data.riskLimits.minimum_confidence),
      detail: "Agent intent gate",
      tone: "neutral",
    },
    {
      label: "Data quality",
      value: formatPercent(data.riskLimits.minimum_data_quality_score),
      detail: "Observation quality gate",
      tone: "neutral",
    },
    {
      label: "Max weight",
      value: formatPercent(data.riskLimits.max_target_weight),
      detail: "Target exposure cap",
      tone: "warn",
    },
    {
      label: "Daily loss",
      value: formatPercent(data.riskLimits.max_daily_loss),
      detail: "Circuit breaker",
      tone: "danger",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation run={data.run} activeSection="risk" source={data.source} />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <RiskControlPanel runId={runId} limits={data.riskLimits} />

        <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <h2 className="text-xl font-semibold">Active Limits</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <LimitRow
                label="Max order notional"
                value={formatCurrency(data.riskLimits.max_order_notional)}
              />
              <LimitRow
                label="Min order notional"
                value={formatCurrency(data.riskLimits.min_order_notional)}
              />
              <LimitRow
                label="Minimum confidence"
                value={formatPercent(data.riskLimits.minimum_confidence)}
              />
              <LimitRow
                label="Minimum data quality"
                value={formatPercent(
                  data.riskLimits.minimum_data_quality_score,
                )}
              />
              <LimitRow
                label="Maximum target weight"
                value={formatPercent(data.riskLimits.max_target_weight)}
              />
              <LimitRow
                label="Maximum leverage"
                value={`${data.riskLimits.max_leverage}x`}
              />
              <LimitRow
                label="Maximum drawdown"
                value={formatPercent(data.riskLimits.max_drawdown)}
              />
              <LimitRow
                label="Maximum daily loss"
                value={formatPercent(data.riskLimits.max_daily_loss)}
              />
              <LimitRow
                label="Live trading"
                value={
                  data.riskLimits.live_trading_allowed ? "Allowed" : "Blocked"
                }
              />
            </dl>
          </div>

          <div>
            <h2 className="text-xl font-semibold">Latest Review</h2>
            {review === null ? (
              <div className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
                No risk review recorded for this run.
              </div>
            ) : (
              <article className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-sm text-[#5f6b66]">
                      Review status /{" "}
                      {formatDateTime(review.created_at_sim_time)}
                    </p>
                    <h3 className="mt-2 text-lg font-semibold">
                      {review.status}
                    </h3>
                  </div>
                  <div className="grid min-w-56 gap-2 text-sm">
                    <LimitRow
                      label="Original weight"
                      value={formatPercent(review.original_target_weight)}
                    />
                    <LimitRow
                      label="Approved weight"
                      value={formatPercent(review.approved_target_weight)}
                    />
                  </div>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <RiskList title="Reasons" values={review.reasons} />
                  <RiskList
                    title="Triggered rules"
                    values={review.triggered_rules}
                  />
                </div>
              </article>
            )}
          </div>
        </div>

        <AlertConsole runId={runId} alerts={data.alerts} />
      </section>
    </main>
  );
}

/**
 * Render risk limit and lifecycle controls.
 *
 * @param props - Risk control props.
 * @returns Risk control panel.
 */
function RiskControlPanel({
  runId,
  limits,
}: {
  runId: string;
  limits: RiskLimits;
}): ReactElement {
  return (
    <section>
      <h2 className="text-xl font-semibold">Risk Controls</h2>
      <div className="mt-3 grid gap-5 rounded-lg border border-[#d8dee4] bg-white p-5 lg:grid-cols-[1.2fr_0.8fr]">
        <form action={updateRiskLimits} className="grid gap-4">
          <input name="run_id" type="hidden" value={runId} />
          <div className="grid gap-3 md:grid-cols-3">
            <RiskNumberInput
              label="Minimum confidence"
              name="minimum_confidence"
              min="0"
              max="1"
              step="0.01"
              value={String(limits.minimum_confidence)}
            />
            <RiskNumberInput
              label="Minimum data quality"
              name="minimum_data_quality_score"
              min="0"
              max="1"
              step="0.01"
              value={String(limits.minimum_data_quality_score)}
            />
            <RiskNumberInput
              label="Maximum target weight"
              name="max_target_weight"
              min="0"
              max="1"
              step="0.01"
              value={limits.max_target_weight}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <RiskNumberInput
              label="Minimum order notional"
              name="min_order_notional"
              min="0"
              step="1"
              value={limits.min_order_notional}
            />
            <RiskNumberInput
              label="Maximum order notional"
              name="max_order_notional"
              min="0"
              step="1"
              value={limits.max_order_notional}
            />
            <RiskNumberInput
              label="Maximum leverage"
              name="max_leverage"
              min="0.1"
              step="0.1"
              value={limits.max_leverage}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <RiskNumberInput
              label="Maximum drawdown"
              name="max_drawdown"
              min="0"
              step="0.01"
              value={limits.max_drawdown}
            />
            <RiskNumberInput
              label="Maximum daily loss"
              name="max_daily_loss"
              min="0"
              step="0.01"
              value={limits.max_daily_loss}
            />
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63] md:w-auto"
              >
                Update Limits
              </button>
            </div>
          </div>
        </form>
        <div className="grid content-start gap-3 border-t border-[#edf0f2] pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          <h3 className="text-base font-semibold">Run Guard</h3>
          <form action={submitRiskRunStatus}>
            <input name="run_id" type="hidden" value={runId} />
            <input name="command" type="hidden" value="pause" />
            <button
              type="submit"
              className="w-full rounded-md border border-[#c2574b] px-4 py-2 text-sm font-semibold text-[#9d3128] hover:bg-[#fff5f3]"
            >
              Pause From Risk
            </button>
          </form>
          <form action={submitRiskRunStatus}>
            <input name="run_id" type="hidden" value={runId} />
            <input name="command" type="hidden" value="resume" />
            <button
              type="submit"
              className="w-full rounded-md border border-[#1f6f8b] px-4 py-2 text-sm font-semibold text-[#1f6f8b] hover:bg-[#eef8fb]"
            >
              Resume From Risk
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}

/**
 * Render one risk number input.
 *
 * @param props - Risk number input props.
 * @returns Risk number input element.
 */
function RiskNumberInput({
  label,
  name,
  min,
  max,
  step,
  value,
}: {
  label: string;
  name: string;
  min: string;
  max?: string;
  step: string;
  value: string;
}): ReactElement {
  return (
    <label className="grid gap-2 text-sm font-medium text-[#17201b]">
      {label}
      <input
        name={name}
        type="number"
        min={min}
        max={max}
        step={step}
        defaultValue={value}
        className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
      />
    </label>
  );
}

/**
 * Render alert creation and status controls.
 *
 * @param props - Alert console props.
 * @returns Alert console element.
 */
function AlertConsole({
  runId,
  alerts,
}: {
  runId: string;
  alerts: Alert[];
}): ReactElement {
  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Alerts</h2>
        <span className="text-sm text-[#5f6b66]">{alerts.length} records</span>
      </div>
      <div className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
        <CreateAlertForm runId={runId} />
        <div className="grid content-start gap-3">
          {alerts.map((alert) => (
            <AlertCard key={alert.alert_id} alert={alert} />
          ))}
          {alerts.length === 0 ? (
            <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
              No alerts are recorded for this run.
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/**
 * Render alert creation form.
 *
 * @param props - Alert creation props.
 * @returns Alert creation form.
 */
function CreateAlertForm({ runId }: { runId: string }): ReactElement {
  return (
    <form
      action={createRiskAlert}
      className="grid content-start gap-4 rounded-lg border border-[#d8dee4] bg-white p-5"
    >
      <input name="run_id" type="hidden" value={runId} />
      <label className="grid gap-2 text-sm font-medium text-[#17201b]">
        Category
        <select
          name="category"
          className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
        >
          {ALERT_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {formatOptionLabel(category)}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-2 text-sm font-medium text-[#17201b]">
        Severity
        <select
          name="severity"
          defaultValue="warning"
          className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
        >
          {ALERT_SEVERITIES.map((severity) => (
            <option key={severity} value={severity}>
              {severity}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-2 text-sm font-medium text-[#17201b]">
        Message
        <textarea
          name="message"
          required
          minLength={1}
          defaultValue="Risk state requires operator review."
          className="min-h-24 rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
        />
      </label>
      <div className="flex justify-end">
        <button
          type="submit"
          className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
        >
          Create Alert
        </button>
      </div>
    </form>
  );
}

/**
 * Render one alert card.
 *
 * @param props - Alert card props.
 * @returns Alert card element.
 */
function AlertCard({ alert }: { alert: Alert }): ReactElement {
  return (
    <article className="rounded-lg border border-[#d8dee4] bg-white p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm text-[#5f6b66]">
            {shortId(alert.alert_id)} /{" "}
            {formatDateTime(alert.created_at_sim_time)}
          </p>
          <h3 className="mt-2 text-lg font-semibold">
            {formatOptionLabel(alert.category)}
          </h3>
          <p className="mt-2 text-sm leading-6 text-[#44504b]">
            {alert.message}
          </p>
        </div>
        <dl className="grid min-w-56 gap-2 text-sm">
          <LimitRow label="Severity" value={alert.severity} />
          <LimitRow label="Status" value={alert.status} />
        </dl>
      </div>
      <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-[#edf0f2] pt-4">
        {ALERT_STATUS_ACTIONS.map((status) => (
          <form key={status} action={updateRiskAlertStatus}>
            <input name="run_id" type="hidden" value={alert.run_id} />
            <input name="alert_id" type="hidden" value={alert.alert_id} />
            <input name="status" type="hidden" value={status} />
            <button
              type="submit"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-semibold text-[#17201b] hover:border-[#1f6f8b] hover:text-[#1f6f8b]"
            >
              {formatOptionLabel(status)}
            </button>
          </form>
        ))}
      </div>
    </article>
  );
}

/**
 * Render one risk limit row.
 *
 * @param props - Limit row props.
 * @returns Limit row element.
 */
function LimitRow({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2">
      <dt className="text-[#5f6b66]">{label}</dt>
      <dd className="font-medium text-[#17201b]">{value}</dd>
    </div>
  );
}

/**
 * Render a compact risk detail list.
 *
 * @param props - Risk list props.
 * @returns Risk list element.
 */
function RiskList({
  title,
  values,
}: {
  title: string;
  values: string[];
}): ReactElement {
  return (
    <div className="border-t border-[#edf0f2] pt-4">
      <h4 className="text-sm font-semibold text-[#17201b]">{title}</h4>
      <ul className="mt-2 grid gap-2 text-sm leading-6 text-[#44504b]">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Update run-level risk limits.
 *
 * @param formData - Submitted risk limit fields.
 */
async function updateRiskLimits(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  await sendRiskJson(`/api/risk/${runId}/limits`, "PUT", {
    minimum_confidence: readBoundedNumber(formData, "minimum_confidence", 0, 1),
    minimum_data_quality_score: readBoundedNumber(
      formData,
      "minimum_data_quality_score",
      0,
      1,
    ),
    max_target_weight: readBoundedNumberString(
      formData,
      "max_target_weight",
      0,
      1,
    ),
    min_order_notional: readNonNegativeNumberString(
      formData,
      "min_order_notional",
    ),
    max_order_notional: readNonNegativeNumberString(
      formData,
      "max_order_notional",
    ),
    max_leverage: readPositiveNumberString(formData, "max_leverage"),
    max_drawdown: readNonNegativeNumberString(formData, "max_drawdown"),
    max_daily_loss: readNonNegativeNumberString(formData, "max_daily_loss"),
  });
  refreshRiskPage(runId);
}

/**
 * Pause or resume a run through risk controls.
 *
 * @param formData - Submitted risk status command fields.
 */
async function submitRiskRunStatus(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  const command = readRiskRunCommand(formData);
  await sendRiskJson(`/api/risk/${runId}/${command}`, "POST", null);
  refreshRiskPage(runId);
}

/**
 * Create a run alert.
 *
 * @param formData - Submitted alert fields.
 */
async function createRiskAlert(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  await sendRiskJson(`/api/risk/${runId}/alerts`, "POST", {
    category: readAlertCategory(formData),
    severity: readAlertSeverity(formData),
    message: readRequiredFormValue(formData, "message"),
  });
  refreshRiskPage(runId);
}

/**
 * Update a run alert status.
 *
 * @param formData - Submitted alert status fields.
 */
async function updateRiskAlertStatus(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  const alertId = readRequiredFormValue(formData, "alert_id");
  await sendRiskJson(`/api/risk/${runId}/alerts/${alertId}/status`, "POST", {
    status: readAlertStatus(formData),
  });
  refreshRiskPage(runId);
}

/**
 * Send a JSON risk mutation request.
 *
 * @param path - Backend API path.
 * @param method - HTTP method.
 * @param payload - Optional JSON payload.
 */
async function sendRiskJson(
  path: string,
  method: "POST" | "PUT",
  payload: Record<string, unknown> | null,
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers:
      payload === null
        ? getOperatorHeaders()
        : {
            ...getOperatorHeaders(),
            "Content-Type": "application/json",
          },
    body: payload === null ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Risk mutation failed: ${await readErrorDetail(response)}`);
  }
}

/**
 * Build operator headers for risk mutations.
 *
 * @returns Backend request headers.
 */
function getOperatorHeaders(): Record<string, string> {
  return {
    "X-Tiko-Role": "operator",
    "X-Tiko-User": "frontend@app.local",
  };
}

/**
 * Revalidate and redirect back to the risk page.
 *
 * @param runId - Simulation run identifier.
 */
function refreshRiskPage(runId: string): never {
  const path = `/simulations/${runId}/risk`;
  revalidatePath(path);
  redirect(path);
}

/**
 * Read a risk run status command.
 *
 * @param formData - Submitted form data.
 * @returns Valid risk run command.
 */
function readRiskRunCommand(formData: FormData): "pause" | "resume" {
  const command = readRequiredFormValue(formData, "command");
  if (command === "pause" || command === "resume") {
    return command;
  }
  throw new Error("command is invalid.");
}

/**
 * Read an alert category from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid alert category.
 */
function readAlertCategory(formData: FormData): AlertCategory {
  const category = readRequiredFormValue(formData, "category");
  if ((ALERT_CATEGORIES as readonly string[]).includes(category)) {
    return category as AlertCategory;
  }
  throw new Error("category is invalid.");
}

/**
 * Read an alert severity from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid alert severity.
 */
function readAlertSeverity(formData: FormData): AlertSeverity {
  const severity = readRequiredFormValue(formData, "severity");
  if ((ALERT_SEVERITIES as readonly string[]).includes(severity)) {
    return severity as AlertSeverity;
  }
  throw new Error("severity is invalid.");
}

/**
 * Read an alert status from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid alert status.
 */
function readAlertStatus(formData: FormData): AlertStatus {
  const status = readRequiredFormValue(formData, "status");
  if ((ALERT_STATUS_ACTIONS as readonly string[]).includes(status)) {
    return status as AlertStatus;
  }
  throw new Error("status is invalid.");
}

/**
 * Read a bounded numeric field.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @param minimum - Inclusive minimum value.
 * @param maximum - Inclusive maximum value.
 * @returns Parsed number.
 */
function readBoundedNumber(
  formData: FormData,
  key: string,
  minimum: number,
  maximum: number,
): number {
  const value = Number(readRequiredFormValue(formData, key));
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read a bounded numeric field as a string.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @param minimum - Inclusive minimum value.
 * @param maximum - Inclusive maximum value.
 * @returns Valid numeric string.
 */
function readBoundedNumberString(
  formData: FormData,
  key: string,
  minimum: number,
  maximum: number,
): string {
  const value = readRequiredFormValue(formData, key);
  const numberValue = Number(value);
  if (
    !Number.isFinite(numberValue) ||
    numberValue < minimum ||
    numberValue > maximum
  ) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read a non-negative numeric field as a string.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Valid numeric string.
 */
function readNonNegativeNumberString(formData: FormData, key: string): string {
  const value = readRequiredFormValue(formData, key);
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue) || numberValue < 0) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read a positive numeric field as a string.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Valid numeric string.
 */
function readPositiveNumberString(formData: FormData, key: string): string {
  const value = readRequiredFormValue(formData, key);
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue) || numberValue <= 0) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read a required string field from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Trimmed field value.
 */
function readRequiredFormValue(formData: FormData, key: string): string {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${key} is required.`);
  }
  return value.trim();
}

/**
 * Format an option key for display.
 *
 * @param value - Option key.
 * @returns Display label.
 */
function formatOptionLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/**
 * Read a concise backend error detail from a failed response.
 *
 * @param response - Failed backend response.
 * @returns Backend error detail.
 */
async function readErrorDetail(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }
  return `HTTP ${response.status}`;
}
