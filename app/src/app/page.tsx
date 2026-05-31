import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchBackendHealth, fetchSimulations } from "@/lib/api-client";
import { formatDataSource, formatDateTime, shortId } from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render the main simulation observation cockpit.
 *
 * @returns Dashboard overview page.
 */
export default async function Home(): Promise<ReactElement> {
  const [health, simulationsResult] = await Promise.all([
    fetchBackendHealth(),
    fetchSimulations(),
  ]);
  const primaryRun = simulationsResult.data[0];
  const metrics: Metric[] = [
    {
      label: "API status",
      value: health.status === "available" ? "Available" : "Offline",
      detail:
        health.status === "available"
          ? `${health.data?.safety_mode ?? "simulation_only"} boundary active`
          : "Rendering deterministic fallback state",
      tone: health.status === "available" ? "good" : "warn",
    },
    {
      label: "Runs",
      value: String(simulationsResult.data.length),
      detail: `${formatDataSource(simulationsResult.source)} / ${shortId(
        primaryRun.run_id,
      )}`,
      tone: "neutral",
    },
    {
      label: "Execution",
      value: "Blocked",
      detail:
        "Private trading, balances, wallets, and signing are outside scope",
      tone: "danger",
    },
    {
      label: "Data",
      value: "Read-only",
      detail: "Public market data can feed simulations without live orders",
      tone: "good",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:px-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-semibold">
                Tiko simulation cockpit
              </h1>
              <p className="mt-2 max-w-3xl text-base leading-7 text-[#5f6b66]">
                Current run observation, simulated account state, risk gates,
                internal orders, fills, and decision traces.
              </p>
            </div>
            <Link
              href={`/simulations/${primaryRun.run_id}/dashboard`}
              className="inline-flex w-fit items-center rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
            >
              Open active run
            </Link>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:grid-cols-[1.1fr_0.9fr] lg:px-8">
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">Simulation Runs</h2>
            <Link
              href="/simulations"
              className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
            >
              View all
            </Link>
          </div>
          <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#eef2f5] text-[#44504b]">
                <tr>
                  <th className="px-4 py-3 font-semibold">Run</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Sim time</th>
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
                    <td className="px-4 py-3">{run.status}</td>
                    <td className="px-4 py-3">
                      {formatDateTime(run.current_sim_time)}
                    </td>
                    <td className="px-4 py-3">{run.symbols.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="grid content-start gap-5">
          <div>
            <h2 className="text-xl font-semibold">Research Control</h2>
            <div className="mt-3 grid gap-2 text-sm">
              <Link
                href="/datasets"
                className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2 font-medium text-[#1f6f8b] hover:text-[#174f63]"
              >
                <span>Datasets</span>
                <span>Open</span>
              </Link>
              <Link
                href="/experiments"
                className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2 font-medium text-[#1f6f8b] hover:text-[#174f63]"
              >
                <span>Experiments</span>
                <span>Open</span>
              </Link>
              <Link
                href="/models"
                className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2 font-medium text-[#1f6f8b] hover:text-[#174f63]"
              >
                <span>Models</span>
                <span>Open</span>
              </Link>
              <Link
                href="/reports"
                className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2 font-medium text-[#1f6f8b] hover:text-[#174f63]"
              >
                <span>Reports</span>
                <span>Open</span>
              </Link>
              <Link
                href="/plugins"
                className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2 font-medium text-[#1f6f8b] hover:text-[#174f63]"
              >
                <span>Plugins</span>
                <span>Open</span>
              </Link>
              <Link
                href="/settings"
                className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2 font-medium text-[#1f6f8b] hover:text-[#174f63]"
              >
                <span>Settings</span>
                <span>Open</span>
              </Link>
            </div>
          </div>
          <div>
            <h2 className="text-xl font-semibold">Safety Boundary</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <BoundaryRow label="Live exchange orders" value="Blocked" />
              <BoundaryRow label="Private account balances" value="Blocked" />
              <BoundaryRow label="Trading credentials" value="Blocked" />
              <BoundaryRow label="Public market data" value="Allowed" />
              <BoundaryRow label="Internal matching" value="Required" />
            </dl>
          </div>
          <div>
            <h2 className="text-xl font-semibold">Build Order</h2>
            <ol className="mt-3 grid gap-2 text-sm text-[#44504b]">
              <BuildStep value="Dataset and experiment APIs" status="Active" />
              <BuildStep value="Long-running observation pages" status="Done" />
              <BuildStep value="Workers and scheduler" status="Next" />
            </ol>
          </div>
        </aside>
      </section>
    </main>
  );
}

/**
 * Render one safety boundary row.
 *
 * @param props - Boundary row props.
 * @returns Boundary row element.
 */
function BoundaryRow({
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

/**
 * Render one build-order status item.
 *
 * @param props - Build step props.
 * @returns Build step element.
 */
function BuildStep({
  value,
  status,
}: {
  value: string;
  status: string;
}): ReactElement {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-[#d8dee4] py-2">
      <span>{value}</span>
      <span className="font-medium text-[#17201b]">{status}</span>
    </li>
  );
}
