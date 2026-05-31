import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { SimulationStreamPanel } from "@/components/realtime/SimulationStreamPanel";
import { fetchRunDashboardData } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  shortId,
} from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render the run-level operational dashboard.
 *
 * @param props - Dynamic route props.
 * @returns Simulation run dashboard page.
 */
export default async function SimulationDashboardPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunDashboardData(runId);
  const metrics: Metric[] = [
    {
      label: "Total equity",
      value: formatCurrency(data.portfolioSummary.total_equity),
      detail: `${formatCurrency(data.portfolioSummary.cash_balance)} cash`,
      tone: "good",
    },
    {
      label: "Drawdown",
      value: formatPercent(data.portfolioSummary.max_drawdown),
      detail: "Maximum simulated account drawdown",
      tone:
        Number(data.portfolioSummary.max_drawdown) > 0.08 ? "warn" : "neutral",
    },
    {
      label: "Decisions",
      value: String(data.decisions.length),
      detail: `${data.orders.length} orders / ${data.fills.length} fills`,
      tone: "neutral",
    },
    {
      label: "Risk",
      value: data.latestRiskReview?.status ?? "No review",
      detail: `Min confidence ${formatPercent(
        data.riskLimits.minimum_confidence,
      )}`,
      tone: data.latestRiskReview?.status === "rejected" ? "danger" : "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="dashboard"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:grid-cols-[1.1fr_0.9fr] lg:px-8">
        <div className="grid content-start gap-5">
          <div className="grid gap-3 md:grid-cols-2">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>

          <div>
            <h2 className="text-xl font-semibold">Recent Decisions</h2>
            <div className="mt-3 overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#eef2f5] text-[#44504b]">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Decision</th>
                    <th className="px-4 py-3 font-semibold">Symbol</th>
                    <th className="px-4 py-3 font-semibold">Action</th>
                    <th className="px-4 py-3 font-semibold">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {data.decisions.slice(0, 5).map((decision) => (
                    <tr
                      key={decision.decision_id}
                      className="border-t border-[#edf0f2]"
                    >
                      <td className="px-4 py-3">
                        {shortId(decision.decision_id)}
                      </td>
                      <td className="px-4 py-3">{decision.symbol}</td>
                      <td className="px-4 py-3">{decision.action}</td>
                      <td className="px-4 py-3">
                        {formatPercent(decision.confidence)}
                      </td>
                    </tr>
                  ))}
                  {data.decisions.length === 0 ? (
                    <tr>
                      <td className="px-4 py-4 text-[#6c7671]" colSpan={4}>
                        No decisions recorded for this run.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <aside className="grid content-start gap-5">
          <div>
            <h2 className="text-xl font-semibold">Runtime</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <RuntimeRow label="Run ID" value={shortId(data.run.run_id)} />
              <RuntimeRow label="Status" value={data.run.status} />
              <RuntimeRow label="Mode" value={data.run.mode} />
              <RuntimeRow
                label="Started"
                value={formatDateTime(data.run.start_sim_time)}
              />
              <RuntimeRow
                label="Sim time"
                value={formatDateTime(data.run.current_sim_time)}
              />
              <RuntimeRow
                label="Speed"
                value={`${data.run.speed_multiplier}x`}
              />
            </dl>
          </div>

          <SimulationStreamPanel
            key={runId}
            runId={runId}
            apiBaseUrl={data.apiBaseUrl}
          />
        </aside>
      </section>
    </main>
  );
}

/**
 * Render one runtime data row.
 *
 * @param props - Runtime row props.
 * @returns Runtime row element.
 */
function RuntimeRow({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2">
      <dt className="text-[#5f6b66]">{label}</dt>
      <dd className="font-medium text-[#17201b]">{value}</dd>
    </div>
  );
}
