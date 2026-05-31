import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunDashboardData } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render simulated portfolio and position state for a run.
 *
 * @param props - Dynamic route props.
 * @returns Portfolio page.
 */
export default async function PortfolioPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunDashboardData(runId);
  const metrics: Metric[] = [
    {
      label: "Equity",
      value: formatCurrency(data.portfolioSummary.total_equity),
      detail: `${formatCurrency(
        data.portfolioSummary.realized_pnl,
      )} realized PnL`,
      tone: "good",
    },
    {
      label: "Cash",
      value: formatCurrency(data.portfolioSummary.cash_balance),
      detail: `${formatCurrency(
        data.portfolioSummary.unrealized_pnl,
      )} unrealized PnL`,
      tone: "neutral",
    },
    {
      label: "Exposure",
      value: formatCurrency(data.portfolioSummary.gross_exposure),
      detail: `${data.positions.length} open positions`,
      tone: "warn",
    },
    {
      label: "Drawdown",
      value: formatPercent(data.portfolioSummary.max_drawdown),
      detail: "Maximum simulated drawdown",
      tone: "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="portfolio"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div>
          <h2 className="text-xl font-semibold">Positions</h2>
          <div className="mt-3 overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#eef2f5] text-[#44504b]">
                <tr>
                  <th className="px-4 py-3 font-semibold">Symbol</th>
                  <th className="px-4 py-3 font-semibold">Side</th>
                  <th className="px-4 py-3 font-semibold">Quantity</th>
                  <th className="px-4 py-3 font-semibold">Entry</th>
                  <th className="px-4 py-3 font-semibold">Notional</th>
                  <th className="px-4 py-3 font-semibold">Leverage</th>
                  <th className="px-4 py-3 font-semibold">Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((position) => (
                  <tr
                    key={position.positionId}
                    className="border-t border-[#edf0f2]"
                  >
                    <td className="px-4 py-3">{position.symbol}</td>
                    <td className="px-4 py-3">{position.side}</td>
                    <td className="px-4 py-3">
                      {formatNumber(position.quantity, 6)}
                    </td>
                    <td className="px-4 py-3">
                      {formatCurrency(position.avgEntryPrice)}
                    </td>
                    <td className="px-4 py-3">
                      {formatCurrency(position.notional)}
                    </td>
                    <td className="px-4 py-3">{position.leverage}x</td>
                    <td className="px-4 py-3">
                      {formatDateTime(position.updatedAtSimTime)}
                    </td>
                  </tr>
                ))}
                {data.positions.length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-[#6c7671]" colSpan={7}>
                      No open simulated positions for this run.
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
