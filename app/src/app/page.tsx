import type { ReactElement } from "react";

import { fetchBackendHealth } from "@/lib/api-client";
import type { BackendHealthState, Metric, RuntimePanel } from "@/lib/types";

const metrics: Metric[] = [
  {
    label: "Execution Mode",
    value: "Simulation Only",
    detail: "No exchange account, wallet, or order-signing capability.",
  },
  {
    label: "Market Data",
    value: "Read Only",
    detail:
      "Public REST/WebSocket input is allowed; private methods are blocked.",
  },
  {
    label: "Current Storage",
    value: "In Memory",
    detail: "Foundation slice uses deterministic process-local run state.",
  },
  {
    label: "Verification",
    value: "Deterministic",
    detail:
      "Schema, connector, runtime, and API tests cover the backend slice.",
  },
];

const runtimePanels: RuntimePanel[] = [
  {
    title: "Simulation Clock",
    value: "1h step",
    detail:
      "Synthetic candles advance simulated time without touching live execution.",
    tone: "good",
  },
  {
    title: "Risk Gate",
    value: "Independent",
    detail: "Low-confidence intents are rejected before portfolio sizing.",
    tone: "good",
  },
  {
    title: "Broker",
    value: "Internal",
    detail:
      "Orders, fills, fees, and PnL are created only by the simulated broker.",
    tone: "neutral",
  },
  {
    title: "Persistence",
    value: "Pending",
    detail:
      "Database migrations are intentionally deferred beyond this first slice.",
    tone: "warn",
  },
];

const eventRows = [
  "Market candle closes from synthetic or read-only public data.",
  "Agent emits structured TradeIntent JSON.",
  "Risk review approves, resizes, rejects, or circuit-blocks.",
  "Portfolio sizing converts approved target exposure to a simulated order.",
  "Sim broker matches internally and ledger updates simulated account state.",
];

/**
 * Render the architecture-aligned dashboard shell.
 *
 * @returns Dashboard page for observing the simulation platform foundation.
 */
export default async function Home(): Promise<ReactElement> {
  const backendHealth = await fetchBackendHealth();

  return (
    <main className="min-h-screen bg-[#f5f7f8] text-[#17201b]">
      <section className="border-b border-[#d9ded8] bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-6 lg:px-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-sm font-medium uppercase tracking-wide text-[#496a5a]">
                Tiko Simulation Control Plane
              </p>
              <h1 className="mt-2 text-3xl font-semibold text-[#17201b]">
                Crypto agent simulation dashboard
              </h1>
              <p className="mt-2 max-w-3xl text-base leading-7 text-[#52605a]">
                The platform may read real public market data, but every
                account, order, fill, fee, risk result, and PnL value is
                simulated inside Tiko.
              </p>
            </div>
            <BackendStatus health={backendHealth} />
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {metrics.map((metric) => (
              <MetricTile key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:grid-cols-[1.2fr_0.8fr] lg:px-8">
        <div className="grid gap-5">
          <section className="rounded-lg border border-[#d9ded8] bg-white p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">Runtime Foundation</h2>
                <p className="mt-1 text-sm text-[#66726d]">
                  First implementation slice aligned to the architecture plan.
                </p>
              </div>
              <span className="rounded-md bg-[#e6f2ec] px-3 py-1 text-sm font-medium text-[#22543b]">
                Phase 1
              </span>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {runtimePanels.map((panel) => (
                <RuntimePanelView key={panel.title} panel={panel} />
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-[#d9ded8] bg-white p-5">
            <h2 className="text-lg font-semibold">Event Flow</h2>
            <ol className="mt-4 grid gap-3">
              {eventRows.map((row, index) => (
                <li
                  key={row}
                  className="grid grid-cols-[2rem_1fr] items-start gap-3"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-md bg-[#1f6f8b] text-sm font-semibold text-white">
                    {index + 1}
                  </span>
                  <span className="pt-1 text-sm leading-6 text-[#44504b]">
                    {row}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="grid gap-5">
          <section className="rounded-lg border border-[#d9ded8] bg-white p-5">
            <h2 className="text-lg font-semibold">Safety Boundary</h2>
            <dl className="mt-4 grid gap-3 text-sm">
              <BoundaryRow label="Real orders" value="Blocked" />
              <BoundaryRow label="Exchange balances" value="Blocked" />
              <BoundaryRow label="Trading credentials" value="Blocked" />
              <BoundaryRow label="Public market data" value="Allowed" />
              <BoundaryRow label="Internal matching" value="Required" />
            </dl>
          </section>

          <section className="rounded-lg border border-[#d9ded8] bg-white p-5">
            <h2 className="text-lg font-semibold">Backend Contract</h2>
            <div className="mt-4 space-y-3 text-sm text-[#44504b]">
              <p>
                FastAPI exposes health, market, simulation, decision, portfolio,
                order, fill, and risk endpoints backed by in-memory services.
              </p>
              <p>
                The dashboard remains usable when the backend is offline and
                will report availability when `NEXT_PUBLIC_API_BASE_URL` is
                reachable.
              </p>
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

/**
 * Render backend health as a compact status panel.
 *
 * @param props - Backend health props.
 * @returns Backend status panel.
 */
function BackendStatus({
  health,
}: {
  health: BackendHealthState;
}): ReactElement {
  const isAvailable = health.status === "available";
  const label = isAvailable ? "Backend Available" : "Backend Offline";
  const detail = isAvailable
    ? `${health.data?.safety_mode ?? "simulation_only"} mode`
    : "Dashboard using static foundation state";

  return (
    <div className="min-w-64 rounded-lg border border-[#d9ded8] bg-[#fbfcfb] p-4">
      <div className="flex items-center gap-2">
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            isAvailable ? "bg-[#2f855a]" : "bg-[#c05621]"
          }`}
        />
        <span className="text-sm font-semibold">{label}</span>
      </div>
      <p className="mt-2 text-sm text-[#66726d]">{detail}</p>
    </div>
  );
}

/**
 * Render one operational metric tile.
 *
 * @param props - Metric tile props.
 * @returns Metric tile element.
 */
function MetricTile({ metric }: { metric: Metric }): ReactElement {
  return (
    <div className="rounded-lg border border-[#d9ded8] bg-[#fbfcfb] p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[#66726d]">
        {metric.label}
      </p>
      <p className="mt-2 text-xl font-semibold text-[#17201b]">
        {metric.value}
      </p>
      <p className="mt-2 text-sm leading-6 text-[#66726d]">{metric.detail}</p>
    </div>
  );
}

/**
 * Render one runtime status panel.
 *
 * @param props - Runtime panel props.
 * @returns Runtime panel element.
 */
function RuntimePanelView({ panel }: { panel: RuntimePanel }): ReactElement {
  const toneClass =
    panel.tone === "good"
      ? "border-l-[#2f855a]"
      : panel.tone === "warn"
        ? "border-l-[#c05621]"
        : "border-l-[#1f6f8b]";

  return (
    <div
      className={`rounded-lg border border-l-4 border-[#d9ded8] ${toneClass} p-4`}
    >
      <p className="text-sm font-medium text-[#66726d]">{panel.title}</p>
      <p className="mt-2 text-lg font-semibold">{panel.value}</p>
      <p className="mt-2 text-sm leading-6 text-[#52605a]">{panel.detail}</p>
    </div>
  );
}

/**
 * Render a safety boundary row.
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
    <div className="flex items-center justify-between gap-3 border-b border-[#eef1ee] pb-3 last:border-b-0 last:pb-0">
      <dt className="text-[#66726d]">{label}</dt>
      <dd className="font-medium text-[#17201b]">{value}</dd>
    </div>
  );
}
