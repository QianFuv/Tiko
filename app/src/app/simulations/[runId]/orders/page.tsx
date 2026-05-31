import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunDashboardData } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render simulated orders and fills for a run.
 *
 * @param props - Dynamic route props.
 * @returns Orders page.
 */
export default async function OrdersPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunDashboardData(runId);
  const totalFees = data.fills.reduce((sum, fill) => sum + Number(fill.fee), 0);
  const metrics: Metric[] = [
    {
      label: "Orders",
      value: String(data.orders.length),
      detail: "Internal simulated broker records",
      tone: "neutral",
    },
    {
      label: "Fills",
      value: String(data.fills.length),
      detail: "Produced by the matching engine",
      tone: "good",
    },
    {
      label: "Fees",
      value: formatCurrency(totalFees),
      detail: "Simulated exchange fee impact",
      tone: "warn",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="orders"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-3">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div>
          <h2 className="text-xl font-semibold">Orders</h2>
          <div className="mt-3 overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#eef2f5] text-[#44504b]">
                <tr>
                  <th className="px-4 py-3 font-semibold">Order</th>
                  <th className="px-4 py-3 font-semibold">Symbol</th>
                  <th className="px-4 py-3 font-semibold">Side</th>
                  <th className="px-4 py-3 font-semibold">Quantity</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((order) => (
                  <tr
                    key={order.order_id}
                    className="border-t border-[#edf0f2]"
                  >
                    <td className="px-4 py-3">{shortId(order.order_id)}</td>
                    <td className="px-4 py-3">{order.symbol}</td>
                    <td className="px-4 py-3">{order.side}</td>
                    <td className="px-4 py-3">
                      {formatNumber(order.quantity, 6)}
                    </td>
                    <td className="px-4 py-3">{order.status}</td>
                    <td className="px-4 py-3">
                      {formatDateTime(order.updated_at_sim_time)}
                    </td>
                  </tr>
                ))}
                {data.orders.length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-[#6c7671]" colSpan={6}>
                      No simulated orders recorded for this run.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h2 className="text-xl font-semibold">Fills</h2>
          <div className="mt-3 overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#eef2f5] text-[#44504b]">
                <tr>
                  <th className="px-4 py-3 font-semibold">Fill</th>
                  <th className="px-4 py-3 font-semibold">Symbol</th>
                  <th className="px-4 py-3 font-semibold">Price</th>
                  <th className="px-4 py-3 font-semibold">Quantity</th>
                  <th className="px-4 py-3 font-semibold">Fee</th>
                  <th className="px-4 py-3 font-semibold">Slippage</th>
                  <th className="px-4 py-3 font-semibold">Time</th>
                </tr>
              </thead>
              <tbody>
                {data.fills.map((fill) => (
                  <tr key={fill.fill_id} className="border-t border-[#edf0f2]">
                    <td className="px-4 py-3">{shortId(fill.fill_id)}</td>
                    <td className="px-4 py-3">{fill.symbol}</td>
                    <td className="px-4 py-3">{formatCurrency(fill.price)}</td>
                    <td className="px-4 py-3">
                      {formatNumber(fill.quantity, 6)}
                    </td>
                    <td className="px-4 py-3">{formatCurrency(fill.fee)}</td>
                    <td className="px-4 py-3">{fill.slippage_bps} bps</td>
                    <td className="px-4 py-3">
                      {formatDateTime(fill.filled_at_sim_time)}
                    </td>
                  </tr>
                ))}
                {data.fills.length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-[#6c7671]" colSpan={7}>
                      No simulated fills recorded for this run.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}
