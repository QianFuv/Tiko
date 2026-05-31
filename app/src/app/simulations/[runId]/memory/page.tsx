import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunMemoryData } from "@/lib/api-client";
import { formatDateTime, formatPercent, shortId } from "@/lib/format";
import type {
  DecisionReview,
  MemoryEntry,
  Metric,
  TradeIntent,
} from "@/lib/types";

/**
 * Render memory entries and posterior review context for a simulation run.
 *
 * @param props - Dynamic route props.
 * @returns Run memory page.
 */
export default async function MemoryPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunMemoryData(runId);
  const reviews = Object.values(data.reviewsByDecisionId).flat();
  const failureEntries = data.memoryEntries.filter(
    (entry) => entry.memory_type === "failure",
  );
  const metrics: Metric[] = [
    {
      label: "Memory",
      value: String(data.memoryEntries.length),
      detail: "Point-in-time auxiliary context",
      tone: "good",
    },
    {
      label: "Reviews",
      value: String(reviews.length),
      detail: "Posterior decision review records",
      tone: "neutral",
    },
    {
      label: "Failures",
      value: String(failureEntries.length),
      detail: "Recorded failure cases",
      tone: failureEntries.length > 0 ? "warn" : "neutral",
    },
    {
      label: "Decisions",
      value: String(data.decisions.length),
      detail: "Potential memory references",
      tone: "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="memory"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <MemoryEntryList entries={data.memoryEntries} />
          <ReviewContext
            decisions={data.decisions}
            reviewsByDecisionId={data.reviewsByDecisionId}
          />
        </div>
      </section>
    </main>
  );
}

/**
 * Render memory entries for one run.
 *
 * @param props - Memory entry list props.
 * @returns Memory entry list element.
 */
function MemoryEntryList({
  entries,
}: {
  entries: MemoryEntry[];
}): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Memory Entries</h2>
        <span className="text-sm text-[#5f6b66]">{entries.length} records</span>
      </div>
      <div className="grid gap-4">
        {entries.map((entry) => (
          <article
            key={entry.memory_id}
            className="rounded-lg border border-[#d8dee4] bg-white p-5"
          >
            <p className="text-sm text-[#5f6b66]">
              {shortId(entry.memory_id)} / {entry.memory_type}
            </p>
            <h3 className="mt-2 text-lg font-semibold">{entry.summary}</h3>
            <dl className="mt-4 grid gap-2 text-sm">
              <MemoryRow
                label="Available"
                value={formatDateTime(entry.available_at_sim_time)}
              />
              <MemoryRow
                label="Decision"
                value={
                  entry.decision_id === null
                    ? "Run-level"
                    : shortId(entry.decision_id)
                }
              />
              <MemoryRow label="Tags" value={entry.tags.join(", ") || "None"} />
            </dl>
            <p className="mt-4 border-t border-[#edf0f2] pt-4 text-sm leading-6 text-[#44504b]">
              {formatRecord(entry.content)}
            </p>
          </article>
        ))}
        {entries.length === 0 ? (
          <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
            No memory entries are available for this run.
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Render decision review context for memory evaluation.
 *
 * @param props - Review context props.
 * @returns Review context element.
 */
function ReviewContext({
  decisions,
  reviewsByDecisionId,
}: {
  decisions: TradeIntent[];
  reviewsByDecisionId: Record<string, DecisionReview[]>;
}): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Decision Context</h2>
        <span className="text-sm text-[#5f6b66]">
          {decisions.length} decisions
        </span>
      </div>
      <div className="grid gap-4">
        {decisions.map((decision) => (
          <DecisionReviewCard
            key={decision.decision_id}
            decision={decision}
            reviews={reviewsByDecisionId[decision.decision_id] ?? []}
          />
        ))}
        {decisions.length === 0 ? (
          <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
            No decisions are available for memory context.
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Render one decision and its posterior reviews.
 *
 * @param props - Decision review card props.
 * @returns Decision review card element.
 */
function DecisionReviewCard({
  decision,
  reviews,
}: {
  decision: TradeIntent;
  reviews: DecisionReview[];
}): ReactElement {
  return (
    <article className="rounded-lg border border-[#d8dee4] bg-white p-5">
      <p className="text-sm text-[#5f6b66]">
        {shortId(decision.decision_id)} / {decision.agent_id}
      </p>
      <h3 className="mt-2 text-lg font-semibold">
        {decision.symbol} {decision.action}
      </h3>
      <p className="mt-2 text-sm leading-6 text-[#44504b]">{decision.thesis}</p>
      <div className="mt-4 grid gap-2 text-sm">
        <MemoryRow
          label="Confidence"
          value={formatPercent(decision.confidence)}
        />
        <MemoryRow
          label="Reviews"
          value={`${reviews.length} posterior records`}
        />
      </div>
      <div className="mt-4 grid gap-2 border-t border-[#edf0f2] pt-4 text-sm leading-6 text-[#44504b]">
        {reviews.map((review) => (
          <p key={review.review_id}>{review.reviewer_summary}</p>
        ))}
        {reviews.length === 0 ? <p>No posterior reviews recorded.</p> : null}
      </div>
    </article>
  );
}

/**
 * Render one memory metadata row.
 *
 * @param props - Memory row props.
 * @returns Memory row element.
 */
function MemoryRow({
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
 * Format structured memory content.
 *
 * @param record - Memory content record.
 * @returns Compact display string.
 */
function formatRecord(record: Record<string, unknown>): string {
  return Object.entries(record)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" / ");
}
