import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { fetchRunDashboardData } from "@/lib/api-client";
import { formatDateTime, formatPercent, shortId } from "@/lib/format";

/**
 * Render the decision trace page for a simulation run.
 *
 * @param props - Dynamic route props.
 * @returns Decision trace page.
 */
export default async function DecisionsPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunDashboardData(runId);

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="decisions"
        source={data.source}
      />
      <section className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-xl font-semibold">Decision Trace</h2>
            <p className="mt-1 text-sm text-[#5f6b66]">
              Structured trade intents and risk-adjacent evidence.
            </p>
          </div>
          <span className="text-sm text-[#5f6b66]">
            {data.decisions.length} records
          </span>
        </div>

        <div className="grid gap-4">
          {data.decisions.map((decision) => (
            <article
              key={decision.decision_id}
              className="rounded-lg border border-[#d8dee4] bg-white p-5"
            >
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
                <div className="grid min-w-56 gap-2 text-sm">
                  <TraceMetric
                    label="Confidence"
                    value={formatPercent(decision.confidence)}
                  />
                  <TraceMetric
                    label="Data quality"
                    value={formatPercent(decision.data_quality_score)}
                  />
                  <TraceMetric
                    label="Target weight"
                    value={formatPercent(decision.target_weight)}
                  />
                  <TraceMetric
                    label="Created"
                    value={formatDateTime(decision.created_at_sim_time)}
                  />
                </div>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <TraceList
                  title="Evidence"
                  values={decision.evidence.map((item) =>
                    Object.entries(item)
                      .map(([key, value]) => `${key}: ${String(value)}`)
                      .join(" / "),
                  )}
                />
                <TraceList
                  title="Invalidation"
                  values={decision.invalidation_conditions}
                />
              </div>
            </article>
          ))}
          {data.decisions.length === 0 ? (
            <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
              No decisions recorded for this run.
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}

/**
 * Render one trace metric row.
 *
 * @param props - Trace metric props.
 * @returns Trace metric row.
 */
function TraceMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#edf0f2] pb-2">
      <span className="text-[#5f6b66]">{label}</span>
      <span className="font-medium text-[#17201b]">{value}</span>
    </div>
  );
}

/**
 * Render a compact trace list.
 *
 * @param props - Trace list props.
 * @returns Trace list element.
 */
function TraceList({
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
