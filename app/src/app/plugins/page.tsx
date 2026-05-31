import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchPlugins } from "@/lib/api-client";
import { formatDataSource, formatDateTime, shortId } from "@/lib/format";
import type {
  Metric,
  PluginPermissions,
  PluginRegistryEntry,
} from "@/lib/types";

/**
 * Render plugin registry and sandbox status.
 *
 * @returns Plugin registry page.
 */
export default async function PluginsPage(): Promise<ReactElement> {
  const pluginsResult = await fetchPlugins();
  const enabledCount = pluginsResult.data.filter(
    (entry) => entry.status === "enabled",
  ).length;
  const passedCount = pluginsResult.data.filter(
    (entry) => entry.sandbox_result.passed,
  ).length;
  const networkCount = pluginsResult.data.filter(
    (entry) => entry.manifest.permissions.network_access,
  ).length;
  const metrics: Metric[] = [
    {
      label: "Plugins",
      value: String(pluginsResult.data.length),
      detail: formatDataSource(pluginsResult.source),
      tone: "neutral",
    },
    {
      label: "Enabled",
      value: String(enabledCount),
      detail: "Active registry entries",
      tone: "good",
    },
    {
      label: "Sandbox passed",
      value: String(passedCount),
      detail: "Validated policy checks",
      tone: "neutral",
    },
    {
      label: "Network access",
      value: String(networkCount),
      detail: "Read-only data connectors only",
      tone: networkCount > 0 ? "warn" : "neutral",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto grid max-w-7xl gap-4 px-5 py-6 lg:px-8">
          <div>
            <h1 className="text-3xl font-semibold">Plugin Registry</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5f6b66]">
              Data, feature, event, analysis, report, and experiment plugins
              with sandbox policy status.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-4 px-5 py-6 lg:px-8">
        {pluginsResult.data.map((entry) => (
          <PluginCard key={entry.plugin_id} entry={entry} />
        ))}
        {pluginsResult.data.length === 0 ? (
          <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
            No plugins are registered.
          </div>
        ) : null}
      </section>
    </main>
  );
}

/**
 * Render one plugin registry entry.
 *
 * @param props - Plugin card props.
 * @returns Plugin card element.
 */
function PluginCard({ entry }: { entry: PluginRegistryEntry }): ReactElement {
  return (
    <article className="rounded-lg border border-[#d8dee4] bg-white p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm text-[#5f6b66]">
            {shortId(entry.plugin_id)} / {entry.manifest.plugin_type}
          </p>
          <h2 className="mt-2 text-xl font-semibold">{entry.manifest.name}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#44504b]">
            {entry.manifest.description}
          </p>
        </div>
        <dl className="grid min-w-72 gap-2 text-sm">
          <PluginRow label="Version" value={entry.manifest.version} />
          <PluginRow label="Status" value={entry.status} />
          <PluginRow
            label="Sandbox"
            value={entry.sandbox_result.passed ? "Passed" : "Failed"}
          />
          <PluginRow label="Created" value={formatDateTime(entry.created_at)} />
        </dl>
      </div>

      <div className="mt-5 grid gap-5 border-t border-[#edf0f2] pt-4 lg:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">Permissions</h3>
          <div className="mt-2 grid gap-2 text-sm">
            {buildPermissionLabels(entry.manifest.permissions).map(
              (permission) => (
                <p key={permission} className="text-[#44504b]">
                  {permission}
                </p>
              ),
            )}
          </div>
        </div>
        <div>
          <h3 className="text-sm font-semibold">Sandbox Results</h3>
          <div className="mt-2 grid gap-2 text-sm text-[#44504b]">
            <p>
              Violations: {entry.sandbox_result.violations.join(", ") || "None"}
            </p>
            <p>
              Warnings: {entry.sandbox_result.warnings.join(", ") || "None"}
            </p>
            <p>Output schema: {entry.manifest.output_schema}</p>
          </div>
        </div>
      </div>
    </article>
  );
}

/**
 * Render one plugin metadata row.
 *
 * @param props - Plugin row props.
 * @returns Plugin row element.
 */
function PluginRow({
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
 * Build human-readable permission labels.
 *
 * @param permissions - Plugin permission set.
 * @returns Enabled permission labels.
 */
function buildPermissionLabels(permissions: PluginPermissions): string[] {
  const labels = [
    permissions.read_market_data ? "Read public market data" : null,
    permissions.read_portfolio ? "Read simulated portfolio" : null,
    permissions.write_market_events ? "Write simulated market events" : null,
    permissions.write_features ? "Write derived features" : null,
    permissions.write_orders ? "Write orders" : null,
    permissions.network_access ? "Network access" : null,
    `File system: ${permissions.file_system_access}`,
    `Provider allowlist: ${permissions.provider_allowlist.join(", ") || "None"}`,
  ];
  return labels.filter((label): label is string => label !== null);
}
