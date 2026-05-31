import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunReviewData } from "@/lib/api-client";
import { formatDateTime, formatPercent, shortId } from "@/lib/format";
import type {
  DecisionReview,
  Metric,
  RiskReview,
  TradeIntent,
} from "@/lib/types";

/**
 * Render posterior decision reviews for a simulation run.
 *
 * @param props - Dynamic route props.
 * @returns Run review page.
 */
export default async function ReviewPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunReviewData(runId);
  const reviews = Object.values(data.reviewsByDecisionId).flat();
  const correctReviews = reviews.filter(
    (review) => review.was_correct_directionally,
  );
  const metrics: Metric[] = [
    {
      label: "Decisions",
      value: String(data.decisions.length),
      detail: "Structured intents in this run",
      tone: "neutral",
    },
    {
      label: "Reviews",
      value: String(reviews.length),
      detail: "Posterior review records",
      tone: "good",
    },
    {
      label: "Directional hit rate",
      value:
        reviews.length === 0
          ? "N/A"
          : formatPercent(correctReviews.length / reviews.length),
      detail: "Reviewed decisions only",
      tone: "neutral",
    },
    {
      label: "Risk status",
      value: data.latestRiskReview?.status ?? "No review",
      detail: "Latest independent risk review",
      tone: data.latestRiskReview?.status === "rejected" ? "danger" : "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="review"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <RiskReviewPanel review={data.latestRiskReview} />

          <div>
            <div className="mb-3 flex items-end justify-between gap-3">
              <h2 className="text-xl font-semibold">Posterior Reviews</h2>
              <span className="text-sm text-[#5f6b66]">
                {reviews.length} records
              </span>
            </div>
            <div className="grid gap-4">
              {data.decisions.map((decision) => (
                <DecisionReviewPanel
                  key={decision.decision_id}
                  decision={decision}
                  reviews={data.reviewsByDecisionId[decision.decision_id] ?? []}
                />
              ))}
              {data.decisions.length === 0 ? (
                <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
                  No decisions are available for posterior review.
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

/**
 * Render latest independent risk review context.
 *
 * @param props - Risk review panel props.
 * @returns Risk review panel element.
 */
function RiskReviewPanel({
  review,
}: {
  review: RiskReview | null;
}): ReactElement {
  return (
    <div>
      <h2 className="text-xl font-semibold">Risk Context</h2>
      {review === null ? (
        <div className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
          No independent risk review has been recorded for this run.
        </div>
      ) : (
        <article className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5">
          <p className="text-sm text-[#5f6b66]">
            {shortId(review.review_id)} /{" "}
            {formatDateTime(review.created_at_sim_time)}
          </p>
          <h3 className="mt-2 text-lg font-semibold">{review.status}</h3>
          <dl className="mt-4 grid gap-2 text-sm">
            <ReviewRow
              label="Original weight"
              value={formatPercent(review.original_target_weight)}
            />
            <ReviewRow
              label="Approved weight"
              value={formatPercent(review.approved_target_weight)}
            />
            <ReviewRow
              label="Rules"
              value={review.triggered_rules.join(", ") || "None"}
            />
          </dl>
        </article>
      )}
    </div>
  );
}

/**
 * Render posterior reviews for one decision.
 *
 * @param props - Decision review panel props.
 * @returns Decision review panel element.
 */
function DecisionReviewPanel({
  decision,
  reviews,
}: {
  decision: TradeIntent;
  reviews: DecisionReview[];
}): ReactElement {
  return (
    <article className="rounded-lg border border-[#d8dee4] bg-white p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm text-[#5f6b66]">
            {shortId(decision.decision_id)} / {decision.agent_id}
          </p>
          <h3 className="mt-2 text-lg font-semibold">
            {decision.symbol} {decision.action}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#44504b]">
            {decision.thesis}
          </p>
        </div>
        <dl className="grid min-w-56 gap-2 text-sm">
          <ReviewRow
            label="Confidence"
            value={formatPercent(decision.confidence)}
          />
          <ReviewRow
            label="Target"
            value={formatPercent(decision.target_weight)}
          />
        </dl>
      </div>

      <div className="mt-4 overflow-hidden rounded-md border border-[#edf0f2]">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#eef2f5] text-[#44504b]">
            <tr>
              <th className="px-4 py-3 font-semibold">Horizon</th>
              <th className="px-4 py-3 font-semibold">Return</th>
              <th className="px-4 py-3 font-semibold">MAE</th>
              <th className="px-4 py-3 font-semibold">MFE</th>
              <th className="px-4 py-3 font-semibold">Correct</th>
            </tr>
          </thead>
          <tbody>
            {reviews.map((review) => (
              <tr key={review.review_id} className="border-t border-[#edf0f2]">
                <td className="px-4 py-3">{review.horizon}</td>
                <td className="px-4 py-3">
                  {formatPercent(review.realized_return)}
                </td>
                <td className="px-4 py-3">
                  {formatPercent(review.max_adverse_excursion)}
                </td>
                <td className="px-4 py-3">
                  {formatPercent(review.max_favorable_excursion)}
                </td>
                <td className="px-4 py-3">
                  {review.was_correct_directionally ? "Yes" : "No"}
                </td>
              </tr>
            ))}
            {reviews.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-[#6c7671]" colSpan={5}>
                  No posterior review metrics are available for this decision.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="mt-4 grid gap-3">
        {reviews.map((review) => (
          <p
            key={review.review_id}
            className="text-sm leading-6 text-[#44504b]"
          >
            {review.reviewer_summary}
          </p>
        ))}
      </div>
    </article>
  );
}

/**
 * Render one review metadata row.
 *
 * @param props - Review row props.
 * @returns Review row element.
 */
function ReviewRow({
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
