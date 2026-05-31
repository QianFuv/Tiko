import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchSettingsData } from "@/lib/api-client";
import {
  formatCurrency,
  formatDataSource,
  formatPercent,
  shortId,
} from "@/lib/format";
import type { Metric } from "@/lib/types";

/**
 * Render runtime settings and safety boundaries.
 *
 * @returns Settings page.
 */
export default async function SettingsPage(): Promise<ReactElement> {
  const data = await fetchSettingsData();
  const metrics: Metric[] = [
    {
      label: "API",
      value: data.health.status === "available" ? "Available" : "Offline",
      detail:
        data.health.data?.safety_mode ?? data.health.error ?? "simulation_only",
      tone: data.health.status === "available" ? "good" : "warn",
    },
    {
      label: "Source",
      value: formatDataSource(data.source),
      detail: "Settings aggregation source",
      tone: "neutral",
    },
    {
      label: "Symbols",
      value: String(data.symbols.symbols.length),
      detail: data.symbols.data_policy,
      tone: "neutral",
    },
    {
      label: "Live trading",
      value: data.riskLimits.live_trading_allowed ? "Allowed" : "Blocked",
      detail: "Platform execution boundary",
      tone: data.riskLimits.live_trading_allowed ? "danger" : "good",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto grid max-w-7xl gap-4 px-5 py-6 lg:px-8">
          <div>
            <h1 className="text-3xl font-semibold">Settings</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5f6b66]">
              Runtime safety boundaries, read-only market data policy, and
              active risk defaults for simulation control.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:grid-cols-[1fr_1fr] lg:px-8">
        <div>
          <h2 className="text-xl font-semibold">Safety Boundary</h2>
          <dl className="mt-3 grid gap-2 text-sm">
            <SettingsRow
              label="Private exchange methods"
              value={
                data.health.data?.private_exchange_methods_allowed
                  ? "Allowed"
                  : "Blocked"
              }
            />
            <SettingsRow
              label="Trading credentials"
              value={
                data.health.data?.trading_credentials_allowed
                  ? "Allowed"
                  : "Blocked"
              }
            />
            <SettingsRow
              label="Market data methods"
              value={
                data.symbols.private_methods_allowed
                  ? "Private allowed"
                  : "Public read-only"
              }
            />
            <SettingsRow label="Primary run" value={shortId(data.run.run_id)} />
          </dl>
        </div>

        <div>
          <h2 className="text-xl font-semibold">Risk Defaults</h2>
          <dl className="mt-3 grid gap-2 text-sm">
            <SettingsRow
              label="Minimum confidence"
              value={formatPercent(data.riskLimits.minimum_confidence)}
            />
            <SettingsRow
              label="Minimum data quality"
              value={formatPercent(data.riskLimits.minimum_data_quality_score)}
            />
            <SettingsRow
              label="Maximum target weight"
              value={formatPercent(data.riskLimits.max_target_weight)}
            />
            <SettingsRow
              label="Minimum order notional"
              value={formatCurrency(data.riskLimits.min_order_notional)}
            />
            <SettingsRow
              label="Maximum order notional"
              value={formatCurrency(data.riskLimits.max_order_notional)}
            />
            <SettingsRow
              label="Maximum drawdown"
              value={formatPercent(data.riskLimits.max_drawdown)}
            />
            <SettingsRow
              label="Maximum daily loss"
              value={formatPercent(data.riskLimits.max_daily_loss)}
            />
          </dl>
        </div>
      </section>
    </main>
  );
}

/**
 * Render one settings row.
 *
 * @param props - Settings row props.
 * @returns Settings row element.
 */
function SettingsRow({
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
