import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchModelDetailData } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { DatasetRecord, Metric } from "@/lib/types";

/**
 * Render model registry details, metrics, datasets, and artifact metadata.
 *
 * @param props - Dynamic route props.
 * @returns Model detail page.
 */
export default async function ModelDetailPage({
  params,
}: {
  params: Promise<{ modelId: string }>;
}): Promise<ReactElement> {
  const { modelId } = await params;
  const data = await fetchModelDetailData(modelId);
  const metrics: Metric[] = [
    {
      label: "Status",
      value: data.model.status,
      detail: "Simulation-only promotion state",
      tone: data.model.status === "paper_enabled" ? "good" : "neutral",
    },
    {
      label: "Type",
      value: data.model.model_type,
      detail: data.model.algorithm,
      tone: "neutral",
    },
    {
      label: "Metrics",
      value: formatNumber(Object.keys(data.model.metrics).length, 0),
      detail: "Recorded validation metrics",
      tone: "neutral",
    },
    {
      label: "Source",
      value: formatDataSource(data.source),
      detail: data.model.version,
      tone: "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:px-8">
          <div>
            <Link
              href="/models"
              className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
            >
              Models
            </Link>
            <h1 className="mt-2 text-3xl font-semibold">{data.model.name}</h1>
            <p className="mt-2 text-sm text-[#5f6b66]">
              {shortId(data.model.model_id)} / {data.model.version}
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
            <h2 className="text-xl font-semibold">Model Metadata</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <DetailRow label="Algorithm" value={data.model.algorithm} />
              <DetailRow label="Artifact URI" value={data.model.artifact_uri} />
              <DetailRow
                label="Created"
                value={formatDateTime(data.model.created_at)}
              />
              <DetailRow label="Status" value={data.model.status} />
            </dl>
          </div>
          <KeyValuePanel values={data.model.metrics} />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <DatasetPanel
            title="Training Dataset"
            dataset={data.trainingDataset}
          />
          <DatasetPanel
            title="Validation Dataset"
            dataset={data.validationDataset}
          />
        </div>
      </section>
    </main>
  );
}

/**
 * Render model metric values.
 *
 * @param props - Key-value panel props.
 * @returns Key-value panel element.
 */
function KeyValuePanel({
  values,
}: {
  values: Record<string, unknown>;
}): ReactElement {
  const entries = Object.entries(values);
  return (
    <div>
      <h2 className="text-xl font-semibold">Metrics</h2>
      <dl className="mt-3 grid gap-2 text-sm">
        {entries.map(([key, value]) => (
          <DetailRow key={key} label={key} value={String(value)} />
        ))}
        {entries.length === 0 ? (
          <p className="text-sm text-[#5f6b66]">No metrics recorded.</p>
        ) : null}
      </dl>
    </div>
  );
}

/**
 * Render dataset metadata linked to a model.
 *
 * @param props - Dataset panel props.
 * @returns Dataset panel element.
 */
function DatasetPanel({
  title,
  dataset,
}: {
  title: string;
  dataset: DatasetRecord | null;
}): ReactElement {
  return (
    <div>
      <h2 className="text-xl font-semibold">{title}</h2>
      {dataset === null ? (
        <div className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
          Dataset metadata is unavailable.
        </div>
      ) : (
        <dl className="mt-3 grid gap-2 text-sm">
          <DetailRow label="Name" value={dataset.name} />
          <DetailRow label="Dataset ID" value={shortId(dataset.dataset_id)} />
          <DetailRow label="Status" value={dataset.status} />
          <DetailRow
            label="Rows"
            value={formatNumber(dataset.candle_count, 0)}
          />
        </dl>
      )}
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
