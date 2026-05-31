import { revalidatePath } from "next/cache";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchSimulations, getApiBaseUrl } from "@/lib/api-client";
import {
  formatCurrency,
  formatDataSource,
  formatDateTime,
  shortId,
} from "@/lib/format";
import type { Metric, SimulationRun } from "@/lib/types";

type SimulationCreateMode = "synthetic_market" | "live_simulated_clock";

type SimulationCreatePayload = {
  name: string;
  symbols: string[];
  mode: SimulationCreateMode;
  speed_multiplier: string;
  timeframe: string;
  decision_interval: string;
  initial_equity: string;
};

const CREATE_MODES: SimulationCreateMode[] = [
  "synthetic_market",
  "live_simulated_clock",
];

/**
 * Render the simulation run index.
 *
 * @returns Simulation list page.
 */
export default async function SimulationsPage(): Promise<ReactElement> {
  const simulationsResult = await fetchSimulations();
  const totalEquity = simulationsResult.data.reduce(
    (sum, run) => sum + Number(run.account.total_equity),
    0,
  );
  const metrics: Metric[] = [
    {
      label: "Runs",
      value: String(simulationsResult.data.length),
      detail: formatDataSource(simulationsResult.source),
      tone: "neutral",
    },
    {
      label: "Total simulated equity",
      value: formatCurrency(totalEquity),
      detail: "Aggregated internal account state",
      tone: "good",
    },
    {
      label: "Live trading",
      value: "Disabled",
      detail: "No private exchange method is exposed",
      tone: "danger",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
          <Link
            href="/"
            className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
          >
            Dashboard
          </Link>
          <h1 className="mt-2 text-3xl font-semibold">Simulation runs</h1>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <CreateSimulationPanel />
        <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#eef2f5] text-[#44504b]">
              <tr>
                <th className="px-4 py-3 font-semibold">Run</th>
                <th className="px-4 py-3 font-semibold">Mode</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Equity</th>
                <th className="px-4 py-3 font-semibold">Current time</th>
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
                  <td className="px-4 py-3">{run.mode}</td>
                  <td className="px-4 py-3">{run.status}</td>
                  <td className="px-4 py-3">
                    {formatCurrency(run.account.total_equity)}
                  </td>
                  <td className="px-4 py-3">
                    {formatDateTime(run.current_sim_time)}
                  </td>
                  <td className="px-4 py-3">{run.symbols.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

/**
 * Render the simulation creation panel.
 *
 * @returns Simulation creation panel.
 */
function CreateSimulationPanel(): ReactElement {
  return (
    <section className="mb-6">
      <h2 className="text-xl font-semibold">Create Simulation</h2>
      <form
        action={createSimulationRun}
        className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5"
      >
        <div className="grid gap-3 md:grid-cols-[1fr_14rem_1fr]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Run name
            <input
              name="name"
              required
              minLength={1}
              defaultValue="BTCUSDT research simulation"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Mode
            <select
              name="mode"
              defaultValue="synthetic_market"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              {CREATE_MODES.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Symbols
            <input
              name="symbols"
              required
              minLength={1}
              defaultValue="BTCUSDT, ETHUSDT"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Speed
            <input
              name="speed_multiplier"
              type="number"
              min="0.1"
              step="0.1"
              defaultValue="1"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Timeframe
            <input
              name="timeframe"
              required
              minLength={1}
              defaultValue="1h"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Decision interval
            <input
              name="decision_interval"
              required
              minLength={1}
              defaultValue="1h"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Initial equity
            <input
              name="initial_equity"
              type="number"
              min="1"
              step="1"
              defaultValue="100000"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
        </div>
        <div className="flex justify-end">
          <button
            type="submit"
            className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
          >
            Create Run
          </button>
        </div>
      </form>
    </section>
  );
}

/**
 * Create a simulation run from the index page.
 *
 * @param formData - Submitted simulation creation fields.
 */
async function createSimulationRun(formData: FormData): Promise<void> {
  "use server";

  const payload = buildSimulationCreatePayload(formData);
  const response = await fetch(`${getApiBaseUrl()}/api/simulations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tiko-Role": "operator",
      "X-Tiko-User": "frontend@app.local",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      `Simulation create failed: ${await readErrorDetail(response)}`,
    );
  }
  const run = (await response.json()) as SimulationRun;
  revalidatePath("/simulations");
  redirect(`/simulations/${run.run_id}/dashboard`);
}

/**
 * Build the backend simulation create payload from form data.
 *
 * @param formData - Submitted simulation creation fields.
 * @returns Simulation create payload.
 */
function buildSimulationCreatePayload(
  formData: FormData,
): SimulationCreatePayload {
  const symbols = readRequiredFormValue(formData, "symbols")
    .split(",")
    .map((symbol) => symbol.trim())
    .filter((symbol) => symbol.length > 0);
  if (symbols.length === 0) {
    throw new Error("symbols is required.");
  }
  return {
    name: readRequiredFormValue(formData, "name"),
    symbols,
    mode: readSimulationCreateMode(formData),
    speed_multiplier: readPositiveNumberString(formData, "speed_multiplier"),
    timeframe: readRequiredFormValue(formData, "timeframe"),
    decision_interval: readRequiredFormValue(formData, "decision_interval"),
    initial_equity: readPositiveNumberString(formData, "initial_equity"),
  };
}

/**
 * Read a simulation create mode from form data.
 *
 * @param formData - Submitted form data.
 * @returns Supported simulation create mode.
 */
function readSimulationCreateMode(formData: FormData): SimulationCreateMode {
  const mode = readRequiredFormValue(formData, "mode");
  if ((CREATE_MODES as readonly string[]).includes(mode)) {
    return mode as SimulationCreateMode;
  }
  throw new Error("mode is invalid.");
}

/**
 * Read a positive numeric field as a string.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Positive numeric value string.
 */
function readPositiveNumberString(formData: FormData, key: string): string {
  const value = readRequiredFormValue(formData, key);
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue) || numberValue <= 0) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read a required string field from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Trimmed field value.
 */
function readRequiredFormValue(formData: FormData, key: string): string {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${key} is required.`);
  }
  return value.trim();
}

/**
 * Read a concise backend error detail from a failed response.
 *
 * @param response - Failed backend response.
 * @returns Backend error detail.
 */
async function readErrorDetail(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }
  return `HTTP ${response.status}`;
}
