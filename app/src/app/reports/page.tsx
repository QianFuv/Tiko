import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchReports } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { Metric, ReportArtifact } from "@/lib/types";

/**
 * Render the report artifact overview.
 *
 * @returns Report overview page.
 */
export default async function ReportsPage(): Promise<ReactElement> {
  const reportsResult = await fetchReports();
  const decisionReports = countReportsByType(reportsResult.data, "decision");
  const experimentReports = countReportsByType(reportsResult.data, "experiment");
  const simulationReports = countReportsByType(reportsResult.data, "simulation");
  const metrics: Metric[] = [
    {
      label: "Reports",
      value: String(reportsResult.data.length),
      detail: formatDataSource(reportsResult.source),
      tone: "neutral",
    },
    {
      label: "Simulation",
      value: String(simulationReports),
      detail: "Run-level performance reports",
      tone: simulationReports > 0 ? "good" : "neutral",
    },
    {
      label: "Research",
      value: String(decisionReports + experimentReports),
      detail: "Decision and experiment reports",
      tone: decisionReports + experimentReports > 0 ? "good" : "neutral",
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
          <h1 className="mt-2 text-3xl font-semibold">Reports</h1>
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
                <th className="px-4 py-3 font-semibold">Report</th>
                <th className="px-4 py-3 font-semibold">Type</th>
                <th className="px-4 py-3 font-semibold">Scope</th>
                <th className="px-4 py-3 font-semibold">Sections</th>
                <th className="px-4 py-3 font-semibold">Sim time</th>
                <th className="px-4 py-3 font-semibold">Created</th>
              </tr>
            </thead>
            <tbody>
              {reportsResult.data.map((report) => (
                <tr key={report.report_id} className="border-t border-[#edf0f2]">
                  <td className="px-4 py-3">
                    <p className="font-medium text-[#17201b]">
                      {report.title}
                    </p>
                    <p className="mt-1 max-w-[22rem] text-xs text-[#6c7671]">
                      {report.summary}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <ReportTypeBadge report={report} />
                  </td>
                  <td className="px-4 py-3">
                    <p>{shortId(report.run_id)}</p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {shortId(report.report_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    {formatNumber(Object.keys(report.sections).length, 0)}
                  </td>
                  <td className="px-4 py-3">
                    {formatDateTime(report.created_at_sim_time)}
                  </td>
                  <td className="px-4 py-3">
                    {formatDateTime(report.created_at)}
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
 * Count report artifacts of one type.
 *
 * @param reports - Report artifacts.
 * @param reportType - Report type to count.
 * @returns Matching report count.
 */
function countReportsByType(
  reports: ReportArtifact[],
  reportType: ReportArtifact["report_type"],
): number {
  return reports.filter((report) => report.report_type === reportType).length;
}

/**
 * Render a report type badge.
 *
 * @param props - Report type badge props.
 * @returns Type badge element.
 */
function ReportTypeBadge({
  report,
}: {
  report: ReportArtifact;
}): ReactElement {
  const classes =
    report.report_type === "simulation"
      ? "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]"
      : report.report_type === "decision"
        ? "border-[#b8a2d8] bg-[#f8f5ff] text-[#3f2764]"
        : "border-[#e4b06b] bg-[#fff9ed] text-[#5a390b]";
  return (
    <span className={`rounded-md border px-2 py-1 text-xs font-medium ${classes}`}>
      {report.report_type}
    </span>
  );
}
