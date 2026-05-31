import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunDashboardData } from "@/lib/api-client";
import { formatCurrency, formatDateTime, formatPercent } from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render risk limits and latest risk review for a run.
 *
 * @param props - Dynamic route props.
 * @returns Risk page.
 */
export default async function RiskPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunDashboardData(runId);
  const review = data.latestRiskReview;
  const metrics: Metric[] = [
    {
      label: "Min confidence",
      value: formatPercent(data.riskLimits.minimum_confidence),
      detail: "Agent intent gate",
      tone: "neutral",
    },
    {
      label: "Data quality",
      value: formatPercent(data.riskLimits.minimum_data_quality_score),
      detail: "Observation quality gate",
      tone: "neutral",
    },
    {
      label: "Max weight",
      value: formatPercent(data.riskLimits.max_target_weight),
      detail: "Target exposure cap",
      tone: "warn",
    },
    {
      label: "Daily loss",
      value: formatPercent(data.riskLimits.max_daily_loss),
      detail: "Circuit breaker",
      tone: "danger",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation run={data.run} activeSection="risk" source={data.source} />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <h2 className="text-xl font-semibold">Active Limits</h2>
            <dl className="mt-3 grid gap-2 text-sm">
              <LimitRow
                label="Max order notional"
                value={formatCurrency(data.riskLimits.max_order_notional)}
              />
              <LimitRow
                label="Min order notional"
                value={formatCurrency(data.riskLimits.min_order_notional)}
              />
              <LimitRow
                label="Minimum confidence"
                value={formatPercent(data.riskLimits.minimum_confidence)}
              />
              <LimitRow
                label="Minimum data quality"
                value={formatPercent(
                  data.riskLimits.minimum_data_quality_score,
                )}
              />
              <LimitRow
                label="Maximum target weight"
                value={formatPercent(data.riskLimits.max_target_weight)}
              />
              <LimitRow
                label="Maximum drawdown"
                value={formatPercent(data.riskLimits.max_drawdown)}
              />
              <LimitRow
                label="Maximum daily loss"
                value={formatPercent(data.riskLimits.max_daily_loss)}
              />
              <LimitRow
                label="Live trading"
                value={
                  data.riskLimits.live_trading_allowed ? "Allowed" : "Blocked"
                }
              />
            </dl>
          </div>

          <div>
            <h2 className="text-xl font-semibold">Latest Review</h2>
            {review === null ? (
              <div className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
                No risk review recorded for this run.
              </div>
            ) : (
              <article className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-sm text-[#5f6b66]">
                      Review status /{" "}
                      {formatDateTime(review.created_at_sim_time)}
                    </p>
                    <h3 className="mt-2 text-lg font-semibold">
                      {review.status}
                    </h3>
                  </div>
                  <div className="grid min-w-56 gap-2 text-sm">
                    <LimitRow
                      label="Original weight"
                      value={formatPercent(review.original_target_weight)}
                    />
                    <LimitRow
                      label="Approved weight"
                      value={formatPercent(review.approved_target_weight)}
                    />
                  </div>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <RiskList title="Reasons" values={review.reasons} />
                  <RiskList
                    title="Triggered rules"
                    values={review.triggered_rules}
                  />
                </div>
              </article>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

/**
 * Render one risk limit row.
 *
 * @param props - Limit row props.
 * @returns Limit row element.
 */
function LimitRow({
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
 * Render a compact risk detail list.
 *
 * @param props - Risk list props.
 * @returns Risk list element.
 */
function RiskList({
  title,
  values,
}: {
  title: string;
  values: string[];
}): ReactElement {
  return (
    <div className="border-t border-[#edf0f2] pt-4">
      <h4 className="text-sm font-semibold text-[#17201b]">{title}</h4>
      <ul className="mt-2 grid gap-2 text-sm leading-6 text-[#44504b]">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}
