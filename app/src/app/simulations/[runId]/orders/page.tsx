import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunDashboardData, getApiBaseUrl } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { Metric, SimOrder } from "@/lib/types";

const ACTIVE_ORDER_STATUSES = new Set(["open", "partially_filled"]);

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
  const activeOrders = data.orders.filter(isCancelableOrder);
  const metrics: Metric[] = [
    {
      label: "Orders",
      value: String(data.orders.length),
      detail: "Internal simulated broker records",
      tone: "neutral",
    },
    {
      label: "Active",
      value: String(activeOrders.length),
      detail: "Cancelable simulated orders",
      tone: activeOrders.length > 0 ? "warn" : "neutral",
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
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">Orders</h2>
            <form action={cancelAllOrders}>
              <input name="run_id" type="hidden" value={runId} />
              <button
                type="submit"
                disabled={activeOrders.length === 0}
                className="rounded-md border border-[#b84a4a] px-3 py-2 text-sm font-semibold text-[#9b3030] hover:bg-[#fff1f1] disabled:cursor-not-allowed disabled:border-[#b7c2c8] disabled:text-[#7b8580]"
              >
                Cancel All Active
              </button>
            </form>
          </div>
          <div className="mt-3 overflow-x-auto rounded-lg border border-[#d8dee4] bg-white">
            <table className="min-w-[54rem] w-full text-left text-sm">
              <thead className="bg-[#eef2f5] text-[#44504b]">
                <tr>
                  <th className="px-4 py-3 font-semibold">Order</th>
                  <th className="px-4 py-3 font-semibold">Symbol</th>
                  <th className="px-4 py-3 font-semibold">Side</th>
                  <th className="px-4 py-3 font-semibold">Quantity</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Updated</th>
                  <th className="px-4 py-3 text-right font-semibold">Action</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((order) => {
                  const isCancelable = isCancelableOrder(order);
                  return (
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
                      <td className="px-4 py-3 text-right">
                        {isCancelable ? (
                          <form action={cancelOrder}>
                            <input name="run_id" type="hidden" value={runId} />
                            <input
                              name="order_id"
                              type="hidden"
                              value={order.order_id}
                            />
                            <button
                              type="submit"
                              className="rounded-md border border-[#b84a4a] px-3 py-1.5 text-xs font-semibold text-[#9b3030] hover:bg-[#fff1f1]"
                            >
                              Cancel
                            </button>
                          </form>
                        ) : (
                          <span className="text-sm text-[#7b8580]">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {data.orders.length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-[#6c7671]" colSpan={7}>
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

/**
 * Cancel one simulated order from the orders page.
 *
 * @param formData - Submitted order cancellation fields.
 */
async function cancelOrder(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  const orderId = readRequiredFormValue(formData, "order_id");
  await sendOrderMutation(`/api/orders/${orderId}/cancel`, null);
  refreshOrdersPage(runId);
}

/**
 * Cancel all active simulated orders for the current run.
 *
 * @param formData - Submitted run cancellation fields.
 */
async function cancelAllOrders(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  await sendOrderMutation("/api/orders/cancel-all", { run_id: runId });
  refreshOrdersPage(runId);
}

/**
 * Return whether an order can be canceled.
 *
 * @param order - Simulated order.
 * @returns `true` when the order is active.
 */
function isCancelableOrder(order: SimOrder): boolean {
  return ACTIVE_ORDER_STATUSES.has(order.status);
}

/**
 * Send a JSON order mutation request.
 *
 * @param path - Backend API path.
 * @param payload - Optional JSON payload.
 */
async function sendOrderMutation(
  path: string,
  payload: Record<string, unknown> | null,
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers:
      payload === null
        ? getOperatorHeaders()
        : {
            ...getOperatorHeaders(),
            "Content-Type": "application/json",
          },
    body: payload === null ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      `Order mutation failed: ${await readErrorDetail(response)}`,
    );
  }
}

/**
 * Build operator headers for order mutations.
 *
 * @returns Backend request headers.
 */
function getOperatorHeaders(): Record<string, string> {
  return {
    "X-Tiko-Role": "operator",
    "X-Tiko-User": "frontend@app.local",
  };
}

/**
 * Revalidate and redirect back to the orders page.
 *
 * @param runId - Simulation run identifier.
 */
function refreshOrdersPage(runId: string): never {
  const path = `/simulations/${runId}/orders`;
  revalidatePath(path);
  redirect(path);
}

/**
 * Read a required string value from submitted form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field name.
 * @returns Field value.
 */
function readRequiredFormValue(formData: FormData, key: string): string {
  const value = formData.get(key);
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${key} is required.`);
  }
  return value;
}

/**
 * Read the most useful backend error detail from a response.
 *
 * @param response - Failed backend response.
 * @returns Human-readable error detail.
 */
async function readErrorDetail(response: Response): Promise<string> {
  const fallback = `HTTP ${response.status}`;
  try {
    const payload = (await response.json()) as { detail?: unknown };
    return typeof payload.detail === "string" ? payload.detail : fallback;
  } catch {
    return fallback;
  }
}
