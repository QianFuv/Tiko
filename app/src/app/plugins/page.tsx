import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchPlugins, getApiBaseUrl } from "@/lib/api-client";
import { formatDataSource, formatDateTime, shortId } from "@/lib/format";
import type {
  Metric,
  PluginManifest,
  PluginPermissions,
  PluginRegistryEntry,
} from "@/lib/types";

type PluginType = PluginManifest["plugin_type"];

type PluginOutputSchema =
  | "AnalysisReport"
  | "Candle"
  | "Candle[]"
  | "ExperimentResult"
  | "FeatureSnapshot"
  | "FeatureSnapshot[]"
  | "MarketEvent"
  | "OrderBookSnapshot"
  | "OrderBookSnapshot[]"
  | "ReportArtifact";

type PluginStatusAction = "archived";

const PLUGIN_TYPES: PluginType[] = [
  "market_data_connector",
  "data_import",
  "synthetic_market",
  "feature_calculation",
  "event_generation",
  "analysis_tool",
  "report",
  "experiment",
];
const OUTPUT_SCHEMAS: PluginOutputSchema[] = [
  "AnalysisReport",
  "Candle",
  "Candle[]",
  "ExperimentResult",
  "FeatureSnapshot",
  "FeatureSnapshot[]",
  "MarketEvent",
  "OrderBookSnapshot",
  "OrderBookSnapshot[]",
  "ReportArtifact",
];
const SANDBOX_TESTS = [
  "test_schema_valid",
  "test_no_write_orders",
  "test_no_secret_inputs",
  "test_no_future_events",
  "test_deterministic_seed",
  "test_network_policy",
  "test_approved_directories",
  "test_resource_limits",
] as const;
const STOCHASTIC_PLUGIN_TYPES: PluginType[] = [
  "event_generation",
  "experiment",
  "synthetic_market",
];
const STATUS_ACTIONS: PluginStatusAction[] = ["archived"];

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
        <RegisterPluginPanel />
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
        <div className="grid gap-3">
          <dl className="grid min-w-72 gap-2 text-sm">
            <PluginRow label="Version" value={entry.manifest.version} />
            <PluginRow label="Status" value={entry.status} />
            <PluginRow
              label="Digest"
              value={formatManifestDigest(entry.manifest_digest)}
            />
            <PluginRow
              label="Sandbox"
              value={entry.sandbox_result.passed ? "Passed" : "Failed"}
            />
            <PluginRow
              label="Approved by"
              value={entry.approved_by ?? "Pending"}
            />
            <PluginRow
              label="Approved"
              value={
                entry.approved_at === null
                  ? "Pending"
                  : formatDateTime(entry.approved_at)
              }
            />
            <PluginRow
              label="Created"
              value={formatDateTime(entry.created_at)}
            />
          </dl>
          <div className="flex flex-wrap justify-end gap-2">
            <PluginApprovalForm
              pluginId={entry.plugin_id}
              manifestDigest={entry.manifest_digest}
              disabled={entry.status !== "validated"}
            />
            <PluginStatusForm
              pluginId={entry.plugin_id}
              status="archived"
              disabled={entry.status === "archived"}
            />
          </div>
        </div>
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
 * Render safe plugin registration controls.
 *
 * @returns Plugin registration panel.
 */
function RegisterPluginPanel(): ReactElement {
  return (
    <section className="mb-2">
      <h2 className="text-xl font-semibold">Register Plugin</h2>
      <form
        action={registerPlugin}
        className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5"
      >
        <div className="grid gap-3 lg:grid-cols-[1fr_10rem_14rem]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Name
            <input
              name="name"
              required
              minLength={1}
              defaultValue="synthetic liquidity shock generator"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Version
            <input
              name="version"
              required
              minLength={1}
              defaultValue="0.1.0"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Type
            <select
              name="plugin_type"
              defaultValue="event_generation"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              {PLUGIN_TYPES.map((pluginType) => (
                <option key={pluginType} value={pluginType}>
                  {pluginType}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid gap-3 lg:grid-cols-[16rem_1fr]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Output schema
            <select
              name="output_schema"
              defaultValue="MarketEvent"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              {OUTPUT_SCHEMAS.map((schema) => (
                <option key={schema} value={schema}>
                  {schema}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Inputs
            <input
              name="inputs"
              required
              minLength={1}
              defaultValue="run_id, symbol, current_sim_time, seed"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
        </div>
        <label className="grid gap-2 text-sm font-medium text-[#17201b]">
          Description
          <textarea
            name="description"
            required
            minLength={1}
            defaultValue="Generates deterministic simulated market events for replay and stress testing."
            className="min-h-24 rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
          />
        </label>
        <div className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            CPU seconds
            <input
              name="cpu_time_limit_seconds"
              type="number"
              min="1"
              step="1"
              defaultValue="10"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Memory MB
            <input
              name="memory_limit_mb"
              type="number"
              min="1"
              step="1"
              defaultValue="128"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Wall seconds
            <input
              name="wall_time_limit_seconds"
              type="number"
              min="1"
              step="1"
              defaultValue="30"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <div className="flex items-end justify-end">
            <button
              type="submit"
              className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
            >
              Register Plugin
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}

/**
 * Render a plugin approval form.
 *
 * @param props - Plugin approval action props.
 * @returns Plugin approval action form.
 */
function PluginApprovalForm({
  pluginId,
  manifestDigest,
  disabled,
}: {
  pluginId: string;
  manifestDigest: string;
  disabled: boolean;
}): ReactElement {
  return (
    <form action={approvePlugin}>
      <input name="plugin_id" type="hidden" value={pluginId} />
      <input name="manifest_digest" type="hidden" value={manifestDigest} />
      <button
        type="submit"
        disabled={disabled}
        className="rounded-md bg-[#1f6f8b] px-3 py-2 text-sm font-semibold text-white hover:bg-[#174f63] disabled:cursor-not-allowed disabled:bg-[#b7c2c8]"
      >
        Approve
      </button>
    </form>
  );
}

/**
 * Render a plugin status update form.
 *
 * @param props - Plugin status action props.
 * @returns Plugin status action form.
 */
function PluginStatusForm({
  pluginId,
  status,
  disabled,
}: {
  pluginId: string;
  status: PluginStatusAction;
  disabled: boolean;
}): ReactElement {
  return (
    <form action={updatePluginStatus}>
      <input name="plugin_id" type="hidden" value={pluginId} />
      <input name="status" type="hidden" value={status} />
      <button
        type="submit"
        disabled={disabled}
        className="rounded-md border border-[#1f6f8b] px-3 py-2 text-sm font-semibold text-[#1f6f8b] hover:bg-[#eef8fb] disabled:cursor-not-allowed disabled:border-[#b7c2c8] disabled:text-[#7b8580]"
      >
        Archive
      </button>
    </form>
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
 * Format a manifest digest for compact display.
 *
 * @param digest - Plugin manifest digest.
 * @returns Compact digest label.
 */
function formatManifestDigest(digest: string): string {
  return `${digest.slice(0, 12)}...${digest.slice(-8)}`;
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
    `Approved directories: ${formatList(permissions.approved_directories)}`,
    `Provider allowlist: ${formatList(permissions.provider_allowlist)}`,
    `Method allowlist: ${formatList(permissions.methods_allowlist)}`,
    `Rate limit: ${formatLimit(permissions.rate_limit_per_minute, "per minute")}`,
    `Credential scope: ${permissions.credential_scope}`,
    `CPU limit: ${formatLimit(permissions.cpu_time_limit_seconds, "seconds")}`,
    `Memory limit: ${formatLimit(permissions.memory_limit_mb, "MB")}`,
    `Wall time limit: ${formatLimit(
      permissions.wall_time_limit_seconds,
      "seconds",
    )}`,
  ];
  return labels.filter((label): label is string => label !== null);
}

/**
 * Format a string allowlist for compact display.
 *
 * @param values - Values to display.
 * @returns Comma-separated values or an empty marker.
 */
function formatList(values: string[]): string {
  return values.length > 0 ? values.join(", ") : "None";
}

/**
 * Format an optional numeric sandbox limit.
 *
 * @param value - Numeric limit value.
 * @param unit - Unit label.
 * @returns Human-readable limit text.
 */
function formatLimit(value: number | null, unit: string): string {
  return value === null ? "None" : `${value} ${unit}`;
}

/**
 * Register a sandbox-constrained plugin manifest.
 *
 * @param formData - Submitted plugin registration fields.
 */
async function registerPlugin(formData: FormData): Promise<void> {
  "use server";

  const manifest = buildPluginManifest(formData);
  await sendPluginJson("/api/plugins", manifest);
  refreshPluginsPage();
}

/**
 * Update a plugin registry status.
 *
 * @param formData - Submitted plugin status fields.
 */
async function updatePluginStatus(formData: FormData): Promise<void> {
  "use server";

  const pluginId = readRequiredFormValue(formData, "plugin_id");
  const status = readPluginStatusAction(formData);
  await sendPluginJson(`/api/plugins/${pluginId}/status`, { status });
  refreshPluginsPage();
}

/**
 * Approve a validated plugin registry entry.
 *
 * @param formData - Submitted plugin approval fields.
 */
async function approvePlugin(formData: FormData): Promise<void> {
  "use server";

  const pluginId = readRequiredFormValue(formData, "plugin_id");
  const manifestDigest = readManifestDigest(formData);
  await sendPluginJson(`/api/plugins/${pluginId}/approve`, {
    manifest_digest: manifestDigest,
  });
  refreshPluginsPage();
}

/**
 * Build a plugin manifest from form data.
 *
 * @param formData - Submitted plugin registration fields.
 * @returns Plugin manifest accepted by the sandbox policy.
 */
function buildPluginManifest(formData: FormData): PluginManifest {
  const name = readRequiredFormValue(formData, "name");
  const pluginType = readPluginType(formData);
  const outputSchema = readOutputSchema(formData);
  return {
    name,
    version: readRequiredFormValue(formData, "version"),
    plugin_type: pluginType,
    description: readRequiredFormValue(formData, "description"),
    permissions: buildSafePluginPermissions(formData, name, outputSchema),
    inputs: buildPluginInputs(formData, pluginType, outputSchema),
    output_schema: outputSchema,
    tests: Array.from(SANDBOX_TESTS),
  };
}

/**
 * Build least-privilege plugin permissions for frontend registration.
 *
 * @param formData - Submitted plugin registration fields.
 * @param name - Plugin name.
 * @param outputSchema - Plugin output schema.
 * @returns Safe plugin permissions.
 */
function buildSafePluginPermissions(
  formData: FormData,
  name: string,
  outputSchema: PluginOutputSchema,
): PluginPermissions {
  return {
    read_market_data: true,
    read_portfolio:
      outputSchema === "AnalysisReport" || outputSchema === "ReportArtifact",
    write_market_events: outputSchema === "MarketEvent",
    write_features:
      outputSchema === "FeatureSnapshot" ||
      outputSchema === "FeatureSnapshot[]",
    write_orders: false,
    network_access: false,
    file_system_access: "sandbox",
    approved_directories: [buildApprovedPluginDirectory(name)],
    provider_allowlist: [],
    methods_allowlist: [],
    rate_limit_per_minute: null,
    credential_scope: "none",
    cpu_time_limit_seconds: readPositiveInteger(
      formData,
      "cpu_time_limit_seconds",
    ),
    memory_limit_mb: readPositiveInteger(formData, "memory_limit_mb"),
    wall_time_limit_seconds: readPositiveInteger(
      formData,
      "wall_time_limit_seconds",
    ),
  };
}

/**
 * Build plugin inputs and append inputs needed by sandbox policy tests.
 *
 * @param formData - Submitted plugin registration fields.
 * @param pluginType - Plugin type.
 * @param outputSchema - Plugin output schema.
 * @returns De-duplicated manifest inputs.
 */
function buildPluginInputs(
  formData: FormData,
  pluginType: PluginType,
  outputSchema: PluginOutputSchema,
): string[] {
  const inputs = readCsvList(formData, "inputs");
  if (outputSchema === "MarketEvent") {
    inputs.push("current_sim_time");
  }
  if (STOCHASTIC_PLUGIN_TYPES.includes(pluginType)) {
    inputs.push("seed");
  }
  return Array.from(new Set(inputs));
}

/**
 * Send a plugin mutation request.
 *
 * @param path - Backend API path.
 * @param payload - JSON payload.
 */
async function sendPluginJson(path: string, payload: unknown): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      ...getAdminHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      `Plugin mutation failed: ${await readErrorDetail(response)}`,
    );
  }
}

/**
 * Build admin headers for plugin mutations.
 *
 * @returns Backend request headers.
 */
function getAdminHeaders(): Record<string, string> {
  return {
    "X-Tiko-Role": "admin",
    "X-Tiko-User": "frontend@app.local",
  };
}

/**
 * Revalidate and redirect back to plugins.
 */
function refreshPluginsPage(): never {
  revalidatePath("/plugins");
  redirect("/plugins");
}

/**
 * Read a plugin type from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid plugin type.
 */
function readPluginType(formData: FormData): PluginType {
  const pluginType = readRequiredFormValue(formData, "plugin_type");
  if ((PLUGIN_TYPES as readonly string[]).includes(pluginType)) {
    return pluginType as PluginType;
  }
  throw new Error("plugin_type is invalid.");
}

/**
 * Read an output schema from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid output schema.
 */
function readOutputSchema(formData: FormData): PluginOutputSchema {
  const outputSchema = readRequiredFormValue(formData, "output_schema");
  if ((OUTPUT_SCHEMAS as readonly string[]).includes(outputSchema)) {
    return outputSchema as PluginOutputSchema;
  }
  throw new Error("output_schema is invalid.");
}

/**
 * Read a plugin status action from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid status action.
 */
function readPluginStatusAction(formData: FormData): PluginStatusAction {
  const status = readRequiredFormValue(formData, "status");
  if ((STATUS_ACTIONS as readonly string[]).includes(status)) {
    return status as PluginStatusAction;
  }
  throw new Error("status is invalid.");
}

/**
 * Read a plugin manifest digest from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid manifest digest.
 */
function readManifestDigest(formData: FormData): string {
  const manifestDigest = readRequiredFormValue(formData, "manifest_digest");
  if (/^[a-f0-9]{64}$/.test(manifestDigest)) {
    return manifestDigest;
  }
  throw new Error("manifest_digest is invalid.");
}

/**
 * Build a safe sandbox-relative plugin directory from a plugin name.
 *
 * @param name - Plugin name.
 * @returns Sandbox-relative plugin directory.
 */
function buildApprovedPluginDirectory(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `plugins/${slug.length > 0 ? slug : "plugin"}`;
}

/**
 * Read a positive integer field.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Parsed positive integer.
 */
function readPositiveInteger(formData: FormData, key: string): number {
  const value = Number(readRequiredFormValue(formData, key));
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
}

/**
 * Read a comma-separated string list.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Trimmed list values.
 */
function readCsvList(formData: FormData, key: string): string[] {
  const values = readRequiredFormValue(formData, key)
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  if (values.length === 0) {
    throw new Error(`${key} is required.`);
  }
  return values;
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
