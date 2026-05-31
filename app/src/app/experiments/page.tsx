import { revalidatePath } from "next/cache";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import {
  fetchDatasets,
  fetchExperiments,
  getApiBaseUrl,
} from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type {
  DataSource,
  DatasetRecord,
  ExperimentRecord,
  Metric,
} from "@/lib/types";

type ExperimentKind =
  | "backtest"
  | "walk_forward"
  | "parameter_sweep"
  | "model_evaluation";

type ExperimentCreatePayload = {
  name: string;
  kind: ExperimentKind;
  hypothesis: string;
  dataset_id: string;
  parameters: Record<string, unknown>;
};

const EXPERIMENT_KINDS: ExperimentKind[] = [
  "backtest",
  "walk_forward",
  "parameter_sweep",
  "model_evaluation",
];

/**
 * Render the experiment overview.
 *
 * @returns Experiment overview page.
 */
export default async function ExperimentsPage(): Promise<ReactElement> {
  const [experimentsResult, datasetsResult] = await Promise.all([
    fetchExperiments(),
    fetchDatasets(),
  ]);
  const source = combinePageSource(
    experimentsResult.source,
    datasetsResult.source,
  );
  const datasetNameById = new Map(
    datasetsResult.data.map((dataset) => [dataset.dataset_id, dataset.name]),
  );
  const queuedCount = experimentsResult.data.filter(
    (experiment) => experiment.status === "queued",
  ).length;
  const completedCount = experimentsResult.data.filter(
    (experiment) => experiment.status === "completed",
  ).length;
  const metrics: Metric[] = [
    {
      label: "Experiments",
      value: String(experimentsResult.data.length),
      detail: formatDataSource(source),
      tone: "neutral",
    },
    {
      label: "Queued",
      value: String(queuedCount),
      detail: "Run requests are dispatched outside request handlers",
      tone: queuedCount > 0 ? "warn" : "neutral",
    },
    {
      label: "Completed",
      value: String(completedCount),
      detail: "Recorded research outcomes",
      tone: completedCount > 0 ? "good" : "neutral",
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
          <h1 className="mt-2 text-3xl font-semibold">Experiments</h1>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <CreateExperimentPanel datasets={datasetsResult.data} />
        <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#eef2f5] text-[#44504b]">
              <tr>
                <th className="px-4 py-3 font-semibold">Experiment</th>
                <th className="px-4 py-3 font-semibold">Dataset</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Kind</th>
                <th className="px-4 py-3 font-semibold">Parameters</th>
                <th className="px-4 py-3 font-semibold">Queued</th>
                <th className="px-4 py-3 font-semibold">Action</th>
              </tr>
            </thead>
            <tbody>
              {experimentsResult.data.map((experiment) => (
                <tr
                  key={experiment.experiment_id}
                  className="border-t border-[#edf0f2]"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/experiments/${experiment.experiment_id}`}
                      className="font-medium text-[#1f6f8b] hover:text-[#174f63]"
                    >
                      {experiment.name}
                    </Link>
                    <p className="mt-1 max-w-[20rem] text-xs text-[#6c7671]">
                      {experiment.hypothesis}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <p>
                      {datasetNameById.get(experiment.dataset_id) ??
                        shortId(experiment.dataset_id)}
                    </p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {shortId(experiment.dataset_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <ExperimentStatusBadge experiment={experiment} />
                  </td>
                  <td className="px-4 py-3">{experiment.kind}</td>
                  <td className="px-4 py-3">
                    {formatNumber(Object.keys(experiment.parameters).length, 0)}
                  </td>
                  <td className="px-4 py-3">
                    {experiment.queued_at === null
                      ? "N/A"
                      : formatDateTime(experiment.queued_at)}
                  </td>
                  <td className="px-4 py-3">
                    <form action={queueExperimentRun}>
                      <input
                        name="experiment_id"
                        type="hidden"
                        value={experiment.experiment_id}
                      />
                      <button
                        type="submit"
                        className="rounded-md border border-[#1f6f8b] px-3 py-2 text-sm font-semibold text-[#1f6f8b] hover:bg-[#eef8fb]"
                      >
                        Queue Run
                      </button>
                    </form>
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
 * Render experiment creation controls.
 *
 * @param props - Experiment creation props.
 * @returns Experiment creation panel.
 */
function CreateExperimentPanel({
  datasets,
}: {
  datasets: DatasetRecord[];
}): ReactElement {
  const hasDatasets = datasets.length > 0;

  return (
    <section className="mb-6">
      <h2 className="text-xl font-semibold">Create Experiment</h2>
      <form
        action={createExperiment}
        className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5"
      >
        <div className="grid gap-3 md:grid-cols-[1fr_14rem_1fr]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Name
            <input
              name="name"
              required
              minLength={1}
              defaultValue="Momentum validation"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Kind
            <select
              name="kind"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            >
              {EXPERIMENT_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Dataset
            <select
              name="dataset_id"
              required
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            >
              {datasets.map((dataset) => (
                <option key={dataset.dataset_id} value={dataset.dataset_id}>
                  {dataset.name}
                </option>
              ))}
              {!hasDatasets ? <option value="">No datasets</option> : null}
            </select>
          </label>
        </div>
        <label className="grid gap-2 text-sm font-medium text-[#17201b]">
          Hypothesis
          <textarea
            name="hypothesis"
            required
            minLength={1}
            defaultValue="Momentum remains positive across validation windows."
            disabled={!hasDatasets}
            className="min-h-24 rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
          />
        </label>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Lookback hours
            <input
              name="lookback_hours"
              type="number"
              min="1"
              step="1"
              defaultValue="24"
              disabled={!hasDatasets}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Max target weight
            <input
              name="max_target_weight"
              type="number"
              min="0"
              max="1"
              step="0.01"
              defaultValue="0.12"
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
              Create Experiment
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}

/**
 * Render an experiment status badge.
 *
 * @param props - Status badge props.
 * @returns Status badge element.
 */
function ExperimentStatusBadge({
  experiment,
}: {
  experiment: ExperimentRecord;
}): ReactElement {
  const classes =
    experiment.status === "completed"
      ? "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]"
      : experiment.status === "failed"
        ? "border-[#df8b8b] bg-[#fff5f5] text-[#5d1616]"
        : "border-[#e4b06b] bg-[#fff9ed] text-[#5a390b]";
  return (
    <span
      className={`rounded-md border px-2 py-1 text-xs font-medium ${classes}`}
    >
      {experiment.status}
    </span>
  );
}

/**
 * Combine experiment and dataset data source markers.
 *
 * @param first - First data source marker.
 * @param second - Second data source marker.
 * @returns Combined page-level marker.
 */
function combinePageSource(first: DataSource, second: DataSource): DataSource {
  return first === second ? first : "mixed";
}

/**
 * Create a research experiment.
 *
 * @param formData - Submitted experiment creation fields.
 */
async function createExperiment(formData: FormData): Promise<void> {
  "use server";

  const payload = buildExperimentCreatePayload(formData);
  await sendExperimentJson("/api/experiments", payload);
  refreshExperimentsPage();
}

/**
 * Queue an experiment run.
 *
 * @param formData - Submitted experiment queue fields.
 */
async function queueExperimentRun(formData: FormData): Promise<void> {
  "use server";

  const experimentId = readRequiredFormValue(formData, "experiment_id");
  await sendExperimentJson(`/api/experiments/${experimentId}/run`, null);
  refreshExperimentsPage();
}

/**
 * Build an experiment create payload from form data.
 *
 * @param formData - Submitted experiment creation fields.
 * @returns Experiment create payload.
 */
function buildExperimentCreatePayload(
  formData: FormData,
): ExperimentCreatePayload {
  return {
    name: readRequiredFormValue(formData, "name"),
    kind: readExperimentKind(formData),
    hypothesis: readRequiredFormValue(formData, "hypothesis"),
    dataset_id: readRequiredFormValue(formData, "dataset_id"),
    parameters: buildExperimentParameters(formData),
  };
}

/**
 * Build optional experiment parameters.
 *
 * @param formData - Submitted experiment creation fields.
 * @returns Experiment parameter object.
 */
function buildExperimentParameters(
  formData: FormData,
): Record<string, unknown> {
  const parameters: Record<string, unknown> = {};
  const lookbackHours = readOptionalPositiveInteger(formData, "lookback_hours");
  const maxTargetWeight = readOptionalBoundedNumberString(
    formData,
    "max_target_weight",
    0,
    1,
  );
  if (lookbackHours !== null) {
    parameters.lookback_hours = lookbackHours;
  }
  if (maxTargetWeight !== null) {
    parameters.max_target_weight = maxTargetWeight;
  }
  return parameters;
}

/**
 * Send an experiment mutation request.
 *
 * @param path - Backend API path.
 * @param payload - Optional JSON payload.
 */
async function sendExperimentJson(
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
      `Experiment mutation failed: ${await readErrorDetail(response)}`,
    );
  }
}

/**
 * Build researcher headers for experiment mutations.
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
 * Revalidate and redirect back to experiments.
 */
function refreshExperimentsPage(): never {
  revalidatePath("/experiments");
  redirect("/experiments");
}

/**
 * Read an experiment kind from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid experiment kind.
 */
function readExperimentKind(formData: FormData): ExperimentKind {
  const kind = readRequiredFormValue(formData, "kind");
  if ((EXPERIMENT_KINDS as readonly string[]).includes(kind)) {
    return kind as ExperimentKind;
  }
  throw new Error("kind is invalid.");
}

/**
 * Read a positive integer field.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Parsed integer.
 */
function readOptionalPositiveInteger(
  formData: FormData,
  key: string,
): number | null {
  const rawValue = readOptionalFormValue(formData, key);
  if (rawValue === null) {
    return null;
  }
  const value = Number(rawValue);
  if (!Number.isInteger(value) || value <= 0) {
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
function readOptionalBoundedNumberString(
  formData: FormData,
  key: string,
  minimum: number,
  maximum: number,
): string | null {
  const value = readOptionalFormValue(formData, key);
  if (value === null) {
    return null;
  }
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
