import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchExperimentDetailData } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { Metric, ReportArtifact } from "@/lib/types";

/**
 * Render experiment details, parameters, metrics, and reports.
 *
 * @param props - Dynamic route props.
 * @returns Experiment detail page.
 */
export default async function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ experimentId: string }>;
}): Promise<ReactElement> {
  const { experimentId } = await params;
  const data = await fetchExperimentDetailData(experimentId);
  const metrics: Metric[] = [
    {
      label: "Status",
      value: data.experiment.status,
      detail: data.experiment.kind,
      tone: data.experiment.status === "completed" ? "good" : "neutral",
    },
    {
      label: "Parameters",
      value: formatNumber(Object.keys(data.experiment.parameters).length, 0),
      detail: "Configured experiment inputs",
      tone: "neutral",
    },
    {
      label: "Metrics",
      value: formatNumber(Object.keys(data.experiment.metrics).length, 0),
      detail: "Recorded experiment outputs",
      tone: "neutral",
    },
    {
      label: "Source",
      value: formatDataSource(data.source),
      detail: data.dataset?.name ?? "Dataset unavailable",
      tone: "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:px-8">
          <div>
            <Link
              href="/experiments"
              className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
            >
              Experiments
            </Link>
            <h1 className="mt-2 text-3xl font-semibold">
              {data.experiment.name}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5f6b66]">
              {data.experiment.hypothesis}
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
            <h2 className="text-xl font-semibold">Experiment Metadata</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <DetailRow
                label="Experiment ID"
                value={shortId(data.experiment.experiment_id)}
              />
              <DetailRow label="Kind" value={data.experiment.kind} />
              <DetailRow
                label="Dataset"
                value={
                  data.dataset?.name ?? shortId(data.experiment.dataset_id)
                }
              />
              <DetailRow
                label="Queued"
                value={
                  data.experiment.queued_at === null
                    ? "N/A"
                    : formatDateTime(data.experiment.queued_at)
                }
              />
            </dl>
          </div>
          <KeyValuePanel
            title="Parameters"
            values={data.experiment.parameters}
            emptyText="No parameters configured."
          />
        </div>
        <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <KeyValuePanel
            title="Metrics"
            values={data.experiment.metrics}
            emptyText="No metrics recorded."
          />
          <ReportList reports={data.reports} />
        </div>
      </section>
    </main>
  );
}

/**
 * Render object key-value data.
 *
 * @param props - Key-value panel props.
 * @returns Key-value panel element.
 */
function KeyValuePanel({
  title,
  values,
  emptyText,
}: {
  title: string;
  values: Record<string, unknown>;
  emptyText: string;
}): ReactElement {
  const entries = Object.entries(values);
  return (
    <div>
      <h2 className="text-xl font-semibold">{title}</h2>
      <dl className="mt-3 grid gap-2 text-sm">
        {entries.map(([key, value]) => (
          <DetailRow key={key} label={key} value={String(value)} />
        ))}
        {entries.length === 0 ? (
          <p className="text-sm text-[#5f6b66]">{emptyText}</p>
        ) : null}
      </dl>
    </div>
  );
}

/**
 * Render experiment reports.
 *
 * @param props - Report list props.
 * @returns Report list element.
 */
function ReportList({ reports }: { reports: ReportArtifact[] }): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Reports</h2>
        <span className="text-sm text-[#5f6b66]">{reports.length} records</span>
      </div>
      <div className="grid gap-4">
        {reports.map((report) => (
          <article
            key={report.report_id}
            className="rounded-lg border border-[#d8dee4] bg-white p-5"
          >
            <p className="text-sm text-[#5f6b66]">
              {shortId(report.report_id)} / {formatDateTime(report.created_at)}
            </p>
            <h3 className="mt-2 text-lg font-semibold">{report.title}</h3>
            <p className="mt-2 text-sm leading-6 text-[#44504b]">
              {report.summary}
            </p>
          </article>
        ))}
        {reports.length === 0 ? (
          <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
            No experiment reports are available.
          </div>
        ) : null}
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
