import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunTraceData } from "@/lib/api-client";
import { formatDateTime, shortId } from "@/lib/format";
import type { AgentMessage, DecisionTrace, Metric } from "@/lib/types";

/**
 * Render agent runtime traces for a simulation run.
 *
 * @param props - Dynamic route props.
 * @returns Agent trace page.
 */
export default async function AgentTracePage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunTraceData(runId);
  const messageCount = Object.values(data.messagesByAgentRunId).reduce(
    (total, messages) => total + messages.length,
    0,
  );
  const metrics: Metric[] = [
    {
      label: "Agent runs",
      value: String(data.agentRuns.length),
      detail: "Runtime evaluations linked to decisions",
      tone: "neutral",
    },
    {
      label: "Traces",
      value: String(data.traces.length),
      detail: "Joined decisions, risk, orders, and fills",
      tone: "good",
    },
    {
      label: "Messages",
      value: String(messageCount),
      detail: "Structured observation and assistant messages",
      tone: "neutral",
    },
    {
      label: "Failed",
      value: String(
        data.agentRuns.filter((agentRun) => agentRun.status === "failed")
          .length,
      ),
      detail: "Agent evaluations requiring review",
      tone: data.agentRuns.some((agentRun) => agentRun.status === "failed")
        ? "danger"
        : "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="agent-trace"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
          <div>
            <div className="mb-3 flex items-end justify-between gap-3">
              <h2 className="text-xl font-semibold">Agent Runs</h2>
              <span className="text-sm text-[#5f6b66]">
                {data.agentRuns.length} records
              </span>
            </div>
            <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#eef2f5] text-[#44504b]">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Agent run</th>
                    <th className="px-4 py-3 font-semibold">Agent</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Completed</th>
                  </tr>
                </thead>
                <tbody>
                  {data.agentRuns.map((agentRun) => (
                    <tr
                      key={agentRun.agent_run_id}
                      className="border-t border-[#edf0f2]"
                    >
                      <td className="px-4 py-3">
                        {shortId(agentRun.agent_run_id)}
                      </td>
                      <td className="px-4 py-3">{agentRun.agent_id}</td>
                      <td className="px-4 py-3">{agentRun.status}</td>
                      <td className="px-4 py-3">
                        {formatDateTime(agentRun.completed_at_sim_time)}
                      </td>
                    </tr>
                  ))}
                  {data.agentRuns.length === 0 ? (
                    <tr>
                      <td className="px-4 py-4 text-[#6c7671]" colSpan={4}>
                        No agent runs recorded for this simulation.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-end justify-between gap-3">
              <h2 className="text-xl font-semibold">Decision Traces</h2>
              <span className="text-sm text-[#5f6b66]">
                {data.traces.length} joined artifacts
              </span>
            </div>
            <div className="grid gap-4">
              {data.traces.map((trace) => (
                <TraceCard key={trace.decision.decision_id} trace={trace} />
              ))}
              {data.traces.length === 0 ? (
                <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
                  No trace artifacts are available for this run.
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
 * Render one joined decision trace card.
 *
 * @param props - Trace card props.
 * @returns Trace card element.
 */
function TraceCard({ trace }: { trace: DecisionTrace }): ReactElement {
  return (
    <article className="rounded-lg border border-[#d8dee4] bg-white p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm text-[#5f6b66]">
            {shortId(trace.decision.decision_id)} / {trace.agent_run.agent_id}
          </p>
          <h3 className="mt-2 text-lg font-semibold">
            {trace.decision.symbol} {trace.decision.action}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#44504b]">
            {trace.decision.thesis}
          </p>
        </div>
        <dl className="grid min-w-60 gap-2 text-sm">
          <TraceRow label="Agent status" value={trace.agent_run.status} />
          <TraceRow
            label="Risk"
            value={trace.risk_review?.status ?? "No review"}
          />
          <TraceRow label="Order" value={trace.order?.status ?? "No order"} />
          <TraceRow
            label="Fill"
            value={trace.fill === null ? "No fill" : trace.fill.price}
          />
        </dl>
      </div>
      <TraceMessages messages={trace.messages} />
    </article>
  );
}

/**
 * Render trace messages for one agent run.
 *
 * @param props - Message list props.
 * @returns Message list element.
 */
function TraceMessages({
  messages,
}: {
  messages: AgentMessage[];
}): ReactElement {
  return (
    <div className="mt-4 border-t border-[#edf0f2] pt-4">
      <h4 className="text-sm font-semibold">Messages</h4>
      <div className="mt-3 grid gap-3">
        {messages.map((message) => (
          <div
            key={message.message_id}
            className="rounded-md border border-[#edf0f2] bg-[#fbfcfd] p-3 text-sm"
          >
            <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
              <span className="font-medium text-[#17201b]">{message.role}</span>
              <span className="text-[#5f6b66]">
                {formatDateTime(message.created_at_sim_time)}
              </span>
            </div>
            <p className="mt-2 leading-6 text-[#44504b]">
              {formatRecord(message.content)}
            </p>
          </div>
        ))}
        {messages.length === 0 ? (
          <p className="text-sm text-[#5f6b66]">
            No structured messages are available for this trace.
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Render one trace metadata row.
 *
 * @param props - Trace row props.
 * @returns Trace row element.
 */
function TraceRow({
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
 * Format a record for compact operational display.
 *
 * @param record - Record to render.
 * @returns Compact display string.
 */
function formatRecord(record: Record<string, unknown>): string {
  return Object.entries(record)
    .map(([key, value]) => `${key}: ${formatUnknown(value)}`)
    .join(" / ");
}

/**
 * Format an unknown value for trace display.
 *
 * @param value - Value to format.
 * @returns Display string.
 */
function formatUnknown(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}
