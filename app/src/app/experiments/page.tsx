import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchDatasets, fetchExperiments } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { DataSource, ExperimentRecord, Metric } from "@/lib/types";

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
