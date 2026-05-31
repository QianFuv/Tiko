import { revalidatePath } from "next/cache";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchDatasetDetailData, getApiBaseUrl } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { Candle, Metric } from "@/lib/types";
import type { DatasetRecord, SimulationRun } from "@/lib/types";

type ReplayCreatePayload = {
  name: string;
  symbols: string[];
  mode: "historical_replay";
  dataset_id: string;
};

/**
 * Render dataset details, quality, and candle sample.
 *
 * @param props - Dynamic route props.
 * @returns Dataset detail page.
 */
export default async function DatasetDetailPage({
  params,
}: {
  params: Promise<{ datasetId: string }>;
}): Promise<ReactElement> {
  const { datasetId } = await params;
  const data = await fetchDatasetDetailData(datasetId);
  const metrics: Metric[] = [
    {
      label: "Candles",
      value: formatNumber(data.dataset.candle_count, 0),
      detail: "Normalized dataset rows",
      tone: "good",
    },
    {
      label: "Errors",
      value: formatNumber(data.quality.error_count, 0),
      detail: "Validation error count",
      tone: data.quality.error_count > 0 ? "danger" : "good",
    },
    {
      label: "Warnings",
      value: formatNumber(data.quality.warning_count, 0),
      detail: "Validation warning count",
      tone: data.quality.warning_count > 0 ? "warn" : "neutral",
    },
    {
      label: "Source",
      value: formatDataSource(data.source),
      detail: data.dataset.source,
      tone: "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:px-8">
          <div>
            <Link
              href="/datasets"
              className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
            >
              Datasets
            </Link>
            <h1 className="mt-2 text-3xl font-semibold">{data.dataset.name}</h1>
            <p className="mt-2 text-sm text-[#5f6b66]">
              {shortId(data.dataset.dataset_id)} / {data.dataset.status}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <h2 className="text-xl font-semibold">Dataset Metadata</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <DetailRow label="Source URI" value={data.dataset.source_uri} />
              <DetailRow
                label="Symbols"
                value={data.dataset.symbols.join(", ") || "N/A"}
              />
              <DetailRow
                label="Timeframes"
                value={data.dataset.timeframes.join(", ") || "N/A"}
              />
              <DetailRow
                label="Range"
                value={formatDateRange(
                  data.dataset.start_time,
                  data.dataset.end_time,
                )}
              />
            </dl>
          </div>
          <QualityPanel
            errors={data.quality.error_count}
            warnings={data.quality.warning_count}
            issueCount={data.quality.issues.length}
          />
        </div>
        <ReplayLaunchPanel dataset={data.dataset} />
        <CandleSample candles={data.candles} />
      </section>
    </main>
  );
}

/**
 * Render dataset quality summary.
 *
 * @param props - Quality panel props.
 * @returns Quality panel element.
 */
function QualityPanel({
  errors,
  warnings,
  issueCount,
}: {
  errors: number;
  warnings: number;
  issueCount: number;
}): ReactElement {
  return (
    <div>
      <h2 className="text-xl font-semibold">Quality Report</h2>
      <dl className="mt-3 grid gap-2 text-sm">
        <DetailRow label="Errors" value={formatNumber(errors, 0)} />
        <DetailRow label="Warnings" value={formatNumber(warnings, 0)} />
        <DetailRow label="Issues sampled" value={formatNumber(issueCount, 0)} />
      </dl>
    </div>
  );
}

/**
 * Render historical replay launch controls for one dataset.
 *
 * @param props - Replay launch props.
 * @returns Replay launch panel element.
 */
function ReplayLaunchPanel({
  dataset,
}: {
  dataset: DatasetRecord;
}): ReactElement {
  const isDisabled =
    dataset.status !== "validated" || dataset.symbols.length === 0;

  return (
    <form
      action={createReplayRun}
      className="grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5 md:grid-cols-[1fr_auto]"
    >
      <input name="dataset_id" type="hidden" value={dataset.dataset_id} />
      <input name="symbols" type="hidden" value={dataset.symbols.join(",")} />
      <label className="grid gap-2 text-sm font-medium text-[#17201b]">
        Replay run name
        <input
          name="name"
          required
          minLength={1}
          defaultValue={`${dataset.name} replay`}
          disabled={isDisabled}
          className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
        />
      </label>
      <div className="flex items-end justify-end">
        <button
          type="submit"
          disabled={isDisabled}
          className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63] disabled:cursor-not-allowed disabled:bg-[#9aa8ad]"
        >
          Start Replay
        </button>
      </div>
    </form>
  );
}

/**
 * Render a candle sample table.
 *
 * @param props - Candle sample props.
 * @returns Candle sample element.
 */
function CandleSample({ candles }: { candles: Candle[] }): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Candle Sample</h2>
        <span className="text-sm text-[#5f6b66]">{candles.length} records</span>
      </div>
      <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#eef2f5] text-[#44504b]">
            <tr>
              <th className="px-4 py-3 font-semibold">As of</th>
              <th className="px-4 py-3 font-semibold">Symbol</th>
              <th className="px-4 py-3 font-semibold">Open</th>
              <th className="px-4 py-3 font-semibold">High</th>
              <th className="px-4 py-3 font-semibold">Low</th>
              <th className="px-4 py-3 font-semibold">Close</th>
            </tr>
          </thead>
          <tbody>
            {candles.map((candle) => (
              <tr
                key={`${candle.symbol}-${candle.as_of}`}
                className="border-t border-[#edf0f2]"
              >
                <td className="px-4 py-3">{formatDateTime(candle.as_of)}</td>
                <td className="px-4 py-3">{candle.symbol}</td>
                <td className="px-4 py-3">{formatNumber(candle.open)}</td>
                <td className="px-4 py-3">{formatNumber(candle.high)}</td>
                <td className="px-4 py-3">{formatNumber(candle.low)}</td>
                <td className="px-4 py-3">{formatNumber(candle.close)}</td>
              </tr>
            ))}
            {candles.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-[#6c7671]" colSpan={6}>
                  No candles are available for this dataset.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Render one detail row.
 *
 * @param props - Detail row props.
 * @returns Detail row element.
 */
function DetailRow({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2">
      <dt className="text-[#5f6b66]">{label}</dt>
      <dd className="max-w-[28rem] truncate font-medium text-[#17201b]">
        {value}
      </dd>
    </div>
  );
}

/**
 * Format an optional dataset date range.
 *
 * @param startTime - Optional start timestamp.
 * @param endTime - Optional end timestamp.
 * @returns Display date range.
 */
function formatDateRange(
  startTime: string | null,
  endTime: string | null,
): string {
  if (startTime === null || endTime === null) {
    return "N/A";
  }
  return `${formatDateTime(startTime)} to ${formatDateTime(endTime)}`;
}

/**
 * Create a historical replay run from a dataset detail form.
 *
 * @param formData - Submitted replay launch fields.
 */
async function createReplayRun(formData: FormData): Promise<void> {
  "use server";

  const payload = buildReplayCreatePayload(formData);
  const response = await fetch(`${getApiBaseUrl()}/api/simulations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tiko-Role": "operator",
      "X-Tiko-User": "frontend@app.local",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Replay create failed: ${await readErrorDetail(response)}`);
  }
  const run = (await response.json()) as SimulationRun;
  revalidatePath("/simulations");
  redirect(`/simulations/${run.run_id}/dashboard`);
}

/**
 * Build a simulation create payload from replay launch form data.
 *
 * @param formData - Submitted replay launch fields.
 * @returns Historical replay create payload.
 */
function buildReplayCreatePayload(formData: FormData): ReplayCreatePayload {
  const symbols = readRequiredFormValue(formData, "symbols")
    .split(",")
    .map((symbol) => symbol.trim())
    .filter((symbol) => symbol.length > 0);
  if (symbols.length === 0) {
    throw new Error("symbols is required.");
  }
  return {
    name: readRequiredFormValue(formData, "name"),
    symbols,
    mode: "historical_replay",
    dataset_id: readRequiredFormValue(formData, "dataset_id"),
  };
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
