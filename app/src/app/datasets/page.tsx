import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchDatasetQualityReports, fetchDatasets } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type {
  DataSource,
  DatasetQualityReport,
  Metric,
} from "@/lib/types";

/**
 * Render the dataset quality overview.
 *
 * @returns Dataset overview page.
 */
export default async function DatasetsPage(): Promise<ReactElement> {
  const datasetsResult = await fetchDatasets();
  const qualityResult = await fetchDatasetQualityReports(datasetsResult.data);
  const source = combinePageSource(datasetsResult.source, qualityResult.source);
  const qualityByDatasetId = new Map(
    qualityResult.data.map((report) => [report.dataset_id, report]),
  );
  const totalCandles = datasetsResult.data.reduce(
    (sum, dataset) => sum + dataset.candle_count,
    0,
  );
  const invalidDatasets = datasetsResult.data.filter(
    (dataset) => dataset.status === "invalid",
  ).length;
  const totalIssues = qualityResult.data.reduce(
    (sum, report) => sum + report.error_count + report.warning_count,
    0,
  );
  const metrics: Metric[] = [
    {
      label: "Datasets",
      value: String(datasetsResult.data.length),
      detail: formatDataSource(source),
      tone: "neutral",
    },
    {
      label: "Candles",
      value: formatNumber(totalCandles, 0),
      detail: "Normalized point-in-time rows",
      tone: "good",
    },
    {
      label: "Quality issues",
      value: formatNumber(totalIssues, 0),
      detail: `${invalidDatasets} invalid datasets`,
      tone: invalidDatasets > 0 ? "warn" : "good",
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
          <h1 className="mt-2 text-3xl font-semibold">Datasets</h1>
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
                <th className="px-4 py-3 font-semibold">Dataset</th>
                <th className="px-4 py-3 font-semibold">Source</th>
                <th className="px-4 py-3 font-semibold">Quality</th>
                <th className="px-4 py-3 font-semibold">Range</th>
                <th className="px-4 py-3 font-semibold">Rows</th>
                <th className="px-4 py-3 font-semibold">Symbols</th>
              </tr>
            </thead>
            <tbody>
              {datasetsResult.data.map((dataset) => {
                const quality = qualityByDatasetId.get(dataset.dataset_id);
                return (
                  <tr
                    key={dataset.dataset_id}
                    className="border-t border-[#edf0f2]"
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium text-[#17201b]">
                        {dataset.name}
                      </p>
                      <p className="mt-1 text-xs text-[#6c7671]">
                        {shortId(dataset.dataset_id)}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium uppercase text-[#17201b]">
                        {dataset.source}
                      </p>
                      <p className="mt-1 max-w-[18rem] truncate text-xs text-[#6c7671]">
                        {dataset.source_uri}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-md border px-2 py-1 text-xs font-medium ${
                          dataset.status === "validated"
                            ? "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]"
                            : "border-[#e4b06b] bg-[#fff9ed] text-[#5a390b]"
                        }`}
                      >
                        {dataset.status}
                      </span>
                      <p className="mt-2 text-xs text-[#6c7671]">
                        {formatQuality(quality)}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      {formatDateRange(dataset.start_time, dataset.end_time)}
                    </td>
                    <td className="px-4 py-3">
                      {formatNumber(dataset.candle_count, 0)}
                    </td>
                    <td className="px-4 py-3">
                      <p>{dataset.symbols.join(", ") || "N/A"}</p>
                      <p className="mt-1 text-xs text-[#6c7671]">
                        {dataset.timeframes.join(", ") || "N/A"}
                      </p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

/**
 * Combine dataset and quality data source markers.
 *
 * @param first - First data source marker.
 * @param second - Second data source marker.
 * @returns Combined page-level marker.
 */
function combinePageSource(first: DataSource, second: DataSource): DataSource {
  return first === second ? first : "mixed";
}

/**
 * Format a dataset quality summary.
 *
 * @param quality - Optional quality report.
 * @returns Human-readable quality summary.
 */
function formatQuality(quality: DatasetQualityReport | undefined): string {
  if (quality === undefined) {
    return "No quality report";
  }
  return `${quality.error_count} errors / ${quality.warning_count} warnings`;
}

/**
 * Format a dataset time range.
 *
 * @param startTime - Optional start timestamp.
 * @param endTime - Optional end timestamp.
 * @returns Human-readable time range.
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
