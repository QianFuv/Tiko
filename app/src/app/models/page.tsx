import { revalidatePath } from "next/cache";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchDatasets, fetchModels, getApiBaseUrl } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type {
  DataSource,
  DatasetRecord,
  Metric,
  ModelRegistryEntry,
} from "@/lib/types";

type ModelType = "rl" | "ml" | "rule";

type ModelStatus = "draft" | "validated" | "paper_enabled" | "archived";

type ModelRegisterPayload = {
  name: string;
  version: string;
  model_type: ModelType;
  algorithm: string;
  training_dataset_id: string;
  validation_dataset_id: string;
  metrics: Record<string, unknown>;
  artifact_uri: string;
  status: ModelStatus;
};

const MODEL_TYPES: ModelType[] = ["rl", "ml", "rule"];
const MODEL_STATUSES: ModelStatus[] = [
  "draft",
  "validated",
  "paper_enabled",
  "archived",
];

/**
 * Render the model registry overview.
 *
 * @returns Model registry page.
 */
export default async function ModelsPage(): Promise<ReactElement> {
  const [modelsResult, datasetsResult] = await Promise.all([
    fetchModels(),
    fetchDatasets(),
  ]);
  const source = combinePageSource(modelsResult.source, datasetsResult.source);
  const promotedCount = modelsResult.data.filter(
    (model) => model.status === "paper_enabled",
  ).length;
  const archivedCount = modelsResult.data.filter(
    (model) => model.status === "archived",
  ).length;
  const metrics: Metric[] = [
    {
      label: "Models",
      value: String(modelsResult.data.length),
      detail: formatDataSource(source),
      tone: "neutral",
    },
    {
      label: "Paper eligible",
      value: String(promotedCount),
      detail: "Simulation-only model promotion state",
      tone: promotedCount > 0 ? "good" : "neutral",
    },
    {
      label: "Archived",
      value: String(archivedCount),
      detail: "Removed from active research selection",
      tone: archivedCount > 0 ? "warn" : "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
          <Link
            href="/"
            className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
          >
            Dashboard
          </Link>
          <h1 className="mt-2 text-3xl font-semibold">Models</h1>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <RegisterModelPanel datasets={datasetsResult.data} />
        <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#eef2f5] text-[#44504b]">
              <tr>
                <th className="px-4 py-3 font-semibold">Model</th>
                <th className="px-4 py-3 font-semibold">Type</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Datasets</th>
                <th className="px-4 py-3 font-semibold">Metrics</th>
                <th className="px-4 py-3 font-semibold">Created</th>
                <th className="px-4 py-3 font-semibold">Action</th>
              </tr>
            </thead>
            <tbody>
              {modelsResult.data.map((model) => (
                <tr key={model.model_id} className="border-t border-[#edf0f2]">
                  <td className="px-4 py-3">
                    <Link
                      href={`/models/${model.model_id}`}
                      className="font-medium text-[#1f6f8b] hover:text-[#174f63]"
                    >
                      {model.name}
                    </Link>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {model.version} / {shortId(model.model_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <p>{model.model_type}</p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {model.algorithm}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <ModelStatusBadge model={model} />
                  </td>
                  <td className="px-4 py-3">
                    <p>{shortId(model.training_dataset_id)}</p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      validation {shortId(model.validation_dataset_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    {formatNumber(Object.keys(model.metrics).length, 0)}
                  </td>
                  <td className="px-4 py-3">
                    {formatDateTime(model.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <ModelActionForm
                        modelId={model.model_id}
                        action="promote"
                      />
                      <ModelActionForm
                        modelId={model.model_id}
                        action="archive"
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

/**
 * Render model registration controls.
 *
 * @param props - Model registration props.
 * @returns Model registration panel.
 */
function RegisterModelPanel({
  datasets,
}: {
  datasets: DatasetRecord[];
}): ReactElement {
  const hasDatasets = datasets.length > 0;

  return (
    <section className="mb-6">
      <h2 className="text-xl font-semibold">Register Model</h2>
      <form
        action={registerModel}
        className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5"
      >
        <div className="grid gap-3 md:grid-cols-[1fr_10rem_10rem]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Name
            <input
              name="name"
              required
              minLength={1}
              defaultValue="rule momentum baseline"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Version
            <input
              name="version"
              required
              minLength={1}
              defaultValue="0.1.0"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Type
            <select
              name="model_type"
              defaultValue="rule"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            >
              {MODEL_TYPES.map((modelType) => (
                <option key={modelType} value={modelType}>
                  {modelType}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_12rem]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Training dataset
            <DatasetSelect
              name="training_dataset_id"
              datasets={datasets}
              disabled={!hasDatasets}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Validation dataset
            <DatasetSelect
              name="validation_dataset_id"
              datasets={datasets}
              disabled={!hasDatasets}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Status
            <select
              name="status"
              defaultValue="draft"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            >
              {MODEL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Algorithm
            <input
              name="algorithm"
              required
              minLength={1}
              defaultValue="deterministic_momentum"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Artifact URI
            <input
              name="artifact_uri"
              required
              minLength={1}
              defaultValue="memory://models/rule-momentum-baseline"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Simulated reward
            <input
              name="simulated_reward"
              type="number"
              step="0.01"
              defaultValue="0.12"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Max drawdown
            <input
              name="max_drawdown"
              type="number"
              min="0"
              step="0.01"
              defaultValue="0.03"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <div className="flex items-end justify-end">
            <button
              type="submit"
              disabled={!hasDatasets}
              className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63] disabled:cursor-not-allowed disabled:bg-[#9aa8ad]"
            >
              Register Model
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}

/**
 * Render a dataset select.
 *
 * @param props - Dataset select props.
 * @returns Dataset select element.
 */
function DatasetSelect({
  name,
  datasets,
  disabled,
}: {
  name: string;
  datasets: DatasetRecord[];
  disabled: boolean;
}): ReactElement {
  return (
    <select
      name={name}
      required
      disabled={disabled}
      className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
    >
      {datasets.map((dataset) => (
        <option key={dataset.dataset_id} value={dataset.dataset_id}>
          {dataset.name}
        </option>
      ))}
      {datasets.length === 0 ? <option value="">No datasets</option> : null}
    </select>
  );
}

/**
 * Render one model action form.
 *
 * @param props - Model action form props.
 * @returns Model action form.
 */
function ModelActionForm({
  modelId,
  action,
}: {
  modelId: string;
  action: "promote" | "archive";
}): ReactElement {
  return (
    <form action={submitModelAction}>
      <input name="model_id" type="hidden" value={modelId} />
      <input name="action" type="hidden" value={action} />
      <button
        type="submit"
        className="rounded-md border border-[#1f6f8b] px-3 py-2 text-sm font-semibold text-[#1f6f8b] hover:bg-[#eef8fb]"
      >
        {action === "promote" ? "Promote" : "Archive"}
      </button>
    </form>
  );
}

/**
 * Render a model status badge.
 *
 * @param props - Status badge props.
 * @returns Status badge element.
 */
function ModelStatusBadge({
  model,
}: {
  model: ModelRegistryEntry;
}): ReactElement {
  const classes =
    model.status === "paper_enabled"
      ? "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]"
      : model.status === "archived"
        ? "border-[#df8b8b] bg-[#fff5f5] text-[#5d1616]"
        : "border-[#e4b06b] bg-[#fff9ed] text-[#5a390b]";
  return (
    <span
      className={`rounded-md border px-2 py-1 text-xs font-medium ${classes}`}
    >
      {model.status}
    </span>
  );
}

/**
 * Combine model and dataset data source markers.
 *
 * @param first - First data source marker.
 * @param second - Second data source marker.
 * @returns Combined page-level marker.
 */
function combinePageSource(first: DataSource, second: DataSource): DataSource {
  return first === second ? first : "mixed";
}

/**
 * Register a model.
 *
 * @param formData - Submitted model registration fields.
 */
async function registerModel(formData: FormData): Promise<void> {
  "use server";

  const payload = buildModelRegisterPayload(formData);
  await sendModelJson("/api/models", payload);
  refreshModelsPage();
}

/**
 * Submit a model promote or archive action.
 *
 * @param formData - Submitted model action fields.
 */
async function submitModelAction(formData: FormData): Promise<void> {
  "use server";

  const modelId = readRequiredFormValue(formData, "model_id");
  const action = readModelAction(formData);
  await sendModelJson(`/api/models/${modelId}/${action}`, null);
  refreshModelsPage();
}

/**
 * Build a model register payload from form data.
 *
 * @param formData - Submitted model registration fields.
 * @returns Model register payload.
 */
function buildModelRegisterPayload(formData: FormData): ModelRegisterPayload {
  return {
    name: readRequiredFormValue(formData, "name"),
    version: readRequiredFormValue(formData, "version"),
    model_type: readModelType(formData),
    algorithm: readRequiredFormValue(formData, "algorithm"),
    training_dataset_id: readRequiredFormValue(formData, "training_dataset_id"),
    validation_dataset_id: readRequiredFormValue(
      formData,
      "validation_dataset_id",
    ),
    metrics: buildModelMetrics(formData),
    artifact_uri: readRequiredFormValue(formData, "artifact_uri"),
    status: readModelStatus(formData),
  };
}

/**
 * Build optional model metrics.
 *
 * @param formData - Submitted model registration fields.
 * @returns Model metrics object.
 */
function buildModelMetrics(formData: FormData): Record<string, unknown> {
  const metrics: Record<string, unknown> = {};
  const simulatedReward = readOptionalNumberString(
    formData,
    "simulated_reward",
  );
  const maxDrawdown = readOptionalNonNegativeNumberString(
    formData,
    "max_drawdown",
  );
  if (simulatedReward !== null) {
    metrics.simulated_reward = simulatedReward;
  }
  if (maxDrawdown !== null) {
    metrics.max_drawdown = maxDrawdown;
  }
  return metrics;
}

/**
 * Send a model mutation request.
 *
 * @param path - Backend API path.
 * @param payload - Optional JSON payload.
 */
async function sendModelJson(
  path: string,
  payload: Record<string, unknown> | null,
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers:
      payload === null
        ? getResearcherHeaders()
        : {
            ...getResearcherHeaders(),
            "Content-Type": "application/json",
          },
    body: payload === null ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      `Model mutation failed: ${await readErrorDetail(response)}`,
    );
  }
}

/**
 * Build researcher headers for model mutations.
 *
 * @returns Backend request headers.
 */
function getResearcherHeaders(): Record<string, string> {
  return {
    "X-Tiko-Role": "researcher",
    "X-Tiko-User": "frontend@app.local",
  };
}

/**
 * Revalidate and redirect back to models.
 */
function refreshModelsPage(): never {
  revalidatePath("/models");
  redirect("/models");
}

/**
 * Read a model type from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid model type.
 */
function readModelType(formData: FormData): ModelType {
  const modelType = readRequiredFormValue(formData, "model_type");
  if ((MODEL_TYPES as readonly string[]).includes(modelType)) {
    return modelType as ModelType;
  }
  throw new Error("model_type is invalid.");
}

/**
 * Read a model status from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid model status.
 */
function readModelStatus(formData: FormData): ModelStatus {
  const status = readRequiredFormValue(formData, "status");
  if ((MODEL_STATUSES as readonly string[]).includes(status)) {
    return status as ModelStatus;
  }
  throw new Error("status is invalid.");
}

/**
 * Read a model action from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid model action.
 */
function readModelAction(formData: FormData): "promote" | "archive" {
  const action = readRequiredFormValue(formData, "action");
  if (action === "promote" || action === "archive") {
    return action;
  }
  throw new Error("action is invalid.");
}

/**
 * Read an optional number field as a string.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Number string or null.
 */
function readOptionalNumberString(
  formData: FormData,
  key: string,
): string | null {
  const value = readOptionalFormValue(formData, key);
  if (value === null) {
    return null;
  }
  if (!Number.isFinite(Number(value))) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read an optional non-negative number field as a string.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Number string or null.
 */
function readOptionalNonNegativeNumberString(
  formData: FormData,
  key: string,
): string | null {
  const value = readOptionalNumberString(formData, key);
  if (value === null) {
    return null;
  }
  if (Number(value) < 0) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read an optional string field from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Trimmed value or null.
 */
function readOptionalFormValue(formData: FormData, key: string): string | null {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  return value.trim();
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
