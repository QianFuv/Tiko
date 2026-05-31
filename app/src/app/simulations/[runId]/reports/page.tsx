import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunReportData } from "@/lib/api-client";
import { formatDateTime, shortId } from "@/lib/format";
import type { Metric, ReportArtifact } from "@/lib/types";

/**
 * Render scoped simulation and decision reports for a run.
 *
 * @param props - Dynamic route props.
 * @returns Run reports page.
 */
export default async function RunReportsPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunReportData(runId);
  const reports = [...data.simulationReports, ...data.decisionReports];
  const metrics: Metric[] = [
    {
      label: "Reports",
      value: String(reports.length),
      detail: "Run-scoped report artifacts",
      tone: "good",
    },
    {
      label: "Simulation",
      value: String(data.simulationReports.length),
      detail: "Performance and safety reports",
      tone: "neutral",
    },
    {
      label: "Decision",
      value: String(data.decisionReports.length),
      detail: "Decision trace and outcome reports",
      tone: "neutral",
    },
    {
      label: "Latest",
      value:
        reports.length === 0
          ? "N/A"
          : formatDateTime(reports[reports.length - 1].created_at_sim_time),
      detail: "Most recent report timestamp",
      tone: "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="reports"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <ReportSection
          title="Simulation Reports"
          reports={data.simulationReports}
        />
        <ReportSection
          title="Decision Reports"
          reports={data.decisionReports}
        />
      </section>
    </main>
  );
}

/**
 * Render a report artifact section.
 *
 * @param props - Report section props.
 * @returns Report section element.
 */
function ReportSection({
  title,
  reports,
}: {
  title: string;
  reports: ReportArtifact[];
}): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">{title}</h2>
        <span className="text-sm text-[#5f6b66]">{reports.length} records</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {reports.map((report) => (
          <ReportCard key={report.report_id} report={report} />
        ))}
        {reports.length === 0 ? (
          <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
            No reports are available in this category.
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Render one report artifact card.
 *
 * @param props - Report card props.
 * @returns Report card element.
 */
function ReportCard({ report }: { report: ReportArtifact }): ReactElement {
  return (
    <article className="rounded-lg border border-[#d8dee4] bg-white p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm text-[#5f6b66]">
            {shortId(report.report_id)} / {report.report_type}
          </p>
          <h3 className="mt-2 text-lg font-semibold">{report.title}</h3>
          <p className="mt-2 text-sm leading-6 text-[#44504b]">
            {report.summary}
          </p>
        </div>
        <dl className="grid min-w-56 gap-2 text-sm">
          <ReportRow
            label="Sim time"
            value={formatDateTime(report.created_at_sim_time)}
          />
          <ReportRow
            label="Created"
            value={formatDateTime(report.created_at)}
          />
        </dl>
      </div>
      <div className="mt-4 border-t border-[#edf0f2] pt-4">
        <h4 className="text-sm font-semibold">Sections</h4>
        <div className="mt-2 grid gap-2 text-sm leading-6 text-[#44504b]">
          {Object.entries(report.sections).map(([section, value]) => (
            <p key={section}>
              <span className="font-medium text-[#17201b]">{section}:</span>{" "}
              {formatUnknown(value)}
            </p>
          ))}
        </div>
      </div>
    </article>
  );
}

/**
 * Render one report metadata row.
 *
 * @param props - Report row props.
 * @returns Report row element.
 */
function ReportRow({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#edf0f2] pb-2">
      <dt className="text-[#5f6b66]">{label}</dt>
      <dd className="font-medium text-[#17201b]">{value}</dd>
    </div>
  );
}

/**
 * Format unknown report content for display.
 *
 * @param value - Unknown report section value.
 * @returns Display string.
 */
function formatUnknown(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}
