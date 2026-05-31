import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunReportData, getApiBaseUrl } from "@/lib/api-client";
import { formatDateTime, shortId } from "@/lib/format";
import type { Metric, ReportArtifact, TradeIntent } from "@/lib/types";

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

        <ReportGenerationPanel runId={runId} decisions={data.decisions} />
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
 * Render run-scoped report generation controls.
 *
 * @param props - Report generation props.
 * @returns Report generation panel.
 */
function ReportGenerationPanel({
  runId,
  decisions,
}: {
  runId: string;
  decisions: TradeIntent[];
}): ReactElement {
  const hasDecisions = decisions.length > 0;

  return (
    <section>
      <h2 className="text-xl font-semibold">Generate Reports</h2>
      <div className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5 lg:grid-cols-[0.8fr_1.2fr]">
        <form
          action={createSimulationReport}
          className="grid content-between gap-3"
        >
          <input name="run_id" type="hidden" value={runId} />
          <h3 className="text-base font-semibold">Simulation Report</h3>
          <div>
            <button
              type="submit"
              className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
            >
              Generate Simulation Report
            </button>
          </div>
        </form>
        <form
          action={createDecisionReport}
          className="grid gap-3 border-t border-[#edf0f2] pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0"
        >
          <input name="run_id" type="hidden" value={runId} />
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Decision
            <select
              name="decision_id"
              required
              disabled={!hasDecisions}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b] disabled:bg-[#eef2f5] disabled:text-[#7b8580]"
            >
              {decisions.map((decision) => (
                <option key={decision.decision_id} value={decision.decision_id}>
                  {shortId(decision.decision_id)} / {decision.symbol} /{" "}
                  {decision.action}
                </option>
              ))}
              {!hasDecisions ? <option value="">No decisions</option> : null}
            </select>
          </label>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!hasDecisions}
              className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63] disabled:cursor-not-allowed disabled:bg-[#9aa8ad]"
            >
              Generate Decision Report
            </button>
          </div>
        </form>
      </div>
    </section>
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

/**
 * Create a simulation report and refresh the reports page.
 *
 * @param formData - Submitted report creation fields.
 */
async function createSimulationReport(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  await postReportMutation(`/api/reports/simulations/${runId}`);
  refreshReportsPage(runId);
}

/**
 * Create a decision report and refresh the reports page.
 *
 * @param formData - Submitted report creation fields.
 */
async function createDecisionReport(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  const decisionId = readRequiredFormValue(formData, "decision_id");
  await postReportMutation(`/api/reports/decisions/${decisionId}`);
  refreshReportsPage(runId);
}

/**
 * Post a report mutation to the backend with researcher credentials.
 *
 * @param path - Backend API path.
 */
async function postReportMutation(path: string): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      "X-Tiko-Role": "researcher",
      "X-Tiko-User": "frontend@app.local",
    },
  });
  if (!response.ok) {
    throw new Error(
      `Report mutation failed: ${await readErrorDetail(response)}`,
    );
  }
}

/**
 * Revalidate and redirect back to the reports page.
 *
 * @param runId - Simulation run identifier.
 */
function refreshReportsPage(runId: string): never {
  const path = `/simulations/${runId}/reports`;
  revalidatePath(path);
  redirect(path);
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
