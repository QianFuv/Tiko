import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { SimulationStreamPanel } from "@/components/realtime/SimulationStreamPanel";
import { fetchRunDashboardData } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
  shortId,
} from "@/lib/format";
import type {
  Alert,
  Fill,
  MarketEvent,
  Metric,
  RiskReview,
  RunDashboardData,
  SimOrder,
  TradeIntent,
} from "@/lib/types";

const TIMELINE_ITEM_LIMIT = 12;

type ActivityTimelineTone = "neutral" | "good" | "warn" | "danger";

type ActivityTimelineItem = {
  id: string;
  occurredAt: string;
  label: string;
  title: string;
  detail: string;
  tone: ActivityTimelineTone;
};

const TIMELINE_TONE_CLASSES: Record<ActivityTimelineTone, string> = {
  neutral: "bg-[#7b8790]",
  good: "bg-[#228452]",
  warn: "bg-[#b56a08]",
  danger: "bg-[#b42318]",
};

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
  const timelineItems = buildActivityTimeline(data);
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

          <ActivityTimeline items={timelineItems} />

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
 * Render a compact cross-object activity timeline.
 *
 * @param props - Timeline props.
 * @returns Activity timeline element.
 */
function ActivityTimeline({
  items,
}: {
  items: ActivityTimelineItem[];
}): ReactElement {
  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Run Timeline</h2>
        <span className="text-sm text-[#5f6b66]">
          {items.length} latest records
        </span>
      </div>
      <div className="mt-3 overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
        {items.map((item, index) => (
          <article
            key={item.id}
            className={`grid grid-cols-[auto_1fr] gap-3 px-4 py-3 text-sm ${
              index === 0 ? "" : "border-t border-[#edf0f2]"
            }`}
          >
            <div className="flex w-4 justify-center pt-1">
              <span
                className={`h-2.5 w-2.5 rounded-full ${TIMELINE_TONE_CLASSES[item.tone]}`}
              />
            </div>
            <div className="min-w-0">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <p className="font-semibold text-[#17201b]">{item.title}</p>
                <time className="text-xs text-[#6c7671]">
                  {formatDateTime(item.occurredAt)}
                </time>
              </div>
              <p className="mt-1 break-words text-[#5f6b66]">{item.detail}</p>
              <p className="mt-1 text-xs font-medium uppercase text-[#7b8790]">
                {item.label}
              </p>
            </div>
          </article>
        ))}
        {items.length === 0 ? (
          <div className="px-4 py-5 text-sm text-[#6c7671]">
            No activity recorded for this run.
          </div>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Build timeline items from dashboard aggregate data.
 *
 * @param data - Run dashboard data.
 * @returns Recent timeline items sorted by simulated time.
 */
function buildActivityTimeline(data: RunDashboardData): ActivityTimelineItem[] {
  return [
    ...data.events.map(buildMarketTimelineItem),
    ...data.decisions.map(buildDecisionTimelineItem),
    ...data.orders.map(buildOrderTimelineItem),
    ...data.fills.map(buildFillTimelineItem),
    ...data.alerts.map(buildAlertTimelineItem),
    ...(data.latestRiskReview === null
      ? []
      : [buildRiskTimelineItem(data.latestRiskReview)]),
  ]
    .sort(compareTimelineItems)
    .slice(0, TIMELINE_ITEM_LIMIT);
}

/**
 * Build a market event timeline item.
 *
 * @param event - Market event record.
 * @returns Timeline item.
 */
function buildMarketTimelineItem(event: MarketEvent): ActivityTimelineItem {
  return {
    id: `event-${event.event_id}`,
    occurredAt: event.simulated_time,
    label: "Market",
    title: `${event.type} ${event.symbol ?? "run"}`,
    detail: `${event.source} / confidence ${formatPercent(event.confidence)}`,
    tone: "neutral",
  };
}

/**
 * Build a decision timeline item.
 *
 * @param decision - Trade intent record.
 * @returns Timeline item.
 */
function buildDecisionTimelineItem(
  decision: TradeIntent,
): ActivityTimelineItem {
  return {
    id: `decision-${decision.decision_id}`,
    occurredAt: decision.created_at_sim_time,
    label: "Decision",
    title: `${decision.action} ${decision.symbol}`,
    detail: `Confidence ${formatPercent(decision.confidence)} / ${shortId(
      decision.decision_id,
    )}`,
    tone: decision.confidence >= 0.7 ? "good" : "warn",
  };
}

/**
 * Build a risk review timeline item.
 *
 * @param review - Risk review record.
 * @returns Timeline item.
 */
function buildRiskTimelineItem(review: RiskReview): ActivityTimelineItem {
  return {
    id: `risk-${review.review_id}`,
    occurredAt: review.created_at_sim_time,
    label: "Risk",
    title: `Risk ${review.status}`,
    detail:
      review.triggered_rules.length === 0
        ? "No triggered rules"
        : review.triggered_rules.join(", "),
    tone: review.status === "rejected" ? "danger" : "neutral",
  };
}

/**
 * Build an order timeline item.
 *
 * @param order - Simulated order record.
 * @returns Timeline item.
 */
function buildOrderTimelineItem(order: SimOrder): ActivityTimelineItem {
  return {
    id: `order-${order.order_id}`,
    occurredAt: order.updated_at_sim_time,
    label: "Order",
    title: `${order.side} ${order.order_type} ${order.symbol}`,
    detail: `${order.status} / quantity ${formatNumber(order.quantity, 6)}`,
    tone:
      order.status === "rejected" || order.status === "cancelled"
        ? "warn"
        : "neutral",
  };
}

/**
 * Build a fill timeline item.
 *
 * @param fill - Simulated fill record.
 * @returns Timeline item.
 */
function buildFillTimelineItem(fill: Fill): ActivityTimelineItem {
  return {
    id: `fill-${fill.fill_id}`,
    occurredAt: fill.filled_at_sim_time,
    label: "Fill",
    title: `${fill.side} fill ${fill.symbol}`,
    detail: `${formatCurrency(fill.price)} / fee ${formatCurrency(fill.fee)}`,
    tone: "good",
  };
}

/**
 * Build an alert timeline item.
 *
 * @param alert - Risk alert record.
 * @returns Timeline item.
 */
function buildAlertTimelineItem(alert: Alert): ActivityTimelineItem {
  return {
    id: `alert-${alert.alert_id}`,
    occurredAt: alert.created_at_sim_time,
    label: "Alert",
    title: `${alert.severity} ${alert.category}`,
    detail: `${alert.status} / ${alert.message}`,
    tone: alert.severity === "critical" ? "danger" : "warn",
  };
}

/**
 * Compare timeline items by descending timestamp.
 *
 * @param left - Left timeline item.
 * @param right - Right timeline item.
 * @returns Sort order.
 */
function compareTimelineItems(
  left: ActivityTimelineItem,
  right: ActivityTimelineItem,
): number {
  return (
    parseTimelineTime(right.occurredAt) - parseTimelineTime(left.occurredAt)
  );
}

/**
 * Parse a timeline timestamp.
 *
 * @param value - Timestamp value.
 * @returns Milliseconds since epoch or zero.
 */
function parseTimelineTime(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
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
