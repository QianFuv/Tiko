import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchSimulations } from "@/lib/api-client";
import {
  formatCurrency,
  formatDataSource,
  formatDateTime,
  shortId,
} from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render the simulation run index.
 *
 * @returns Simulation list page.
 */
export default async function SimulationsPage(): Promise<ReactElement> {
  const simulationsResult = await fetchSimulations();
  const totalEquity = simulationsResult.data.reduce(
    (sum, run) => sum + Number(run.account.total_equity),
    0,
  );
  const metrics: Metric[] = [
    {
      label: "Runs",
      value: String(simulationsResult.data.length),
      detail: formatDataSource(simulationsResult.source),
      tone: "neutral",
    },
    {
      label: "Total simulated equity",
      value: formatCurrency(totalEquity),
      detail: "Aggregated internal account state",
      tone: "good",
    },
    {
      label: "Live trading",
      value: "Disabled",
      detail: "No private exchange method is exposed",
      tone: "danger",
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
          <h1 className="mt-2 text-3xl font-semibold">Simulation runs</h1>
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
                <th className="px-4 py-3 font-semibold">Run</th>
                <th className="px-4 py-3 font-semibold">Mode</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Equity</th>
                <th className="px-4 py-3 font-semibold">Current time</th>
                <th className="px-4 py-3 font-semibold">Symbols</th>
              </tr>
            </thead>
            <tbody>
              {simulationsResult.data.map((run) => (
                <tr key={run.run_id} className="border-t border-[#edf0f2]">
                  <td className="px-4 py-3">
                    <Link
                      href={`/simulations/${run.run_id}/dashboard`}
                      className="font-medium text-[#1f6f8b] hover:text-[#174f63]"
                    >
                      {run.name}
                    </Link>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {shortId(run.run_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">{run.mode}</td>
                  <td className="px-4 py-3">{run.status}</td>
                  <td className="px-4 py-3">
                    {formatCurrency(run.account.total_equity)}
                  </td>
                  <td className="px-4 py-3">
                    {formatDateTime(run.current_sim_time)}
                  </td>
                  <td className="px-4 py-3">{run.symbols.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
