import Link from "next/link";
import type { ReactElement } from "react";

import { MetricCard } from "@/components/metric/MetricCard";
import { fetchModels } from "@/lib/api-client";
import {
  formatDataSource,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type { Metric, ModelRegistryEntry } from "@/lib/types";

/**
 * Render the model registry overview.
 *
 * @returns Model registry page.
 */
export default async function ModelsPage(): Promise<ReactElement> {
  const modelsResult = await fetchModels();
  const promotedCount = modelsResult.data.filter(
    (model) => model.status === "paper_enabled",
  ).length;
  const archivedCount = modelsResult.data.filter(
    (model) => model.status === "archived",
  ).length;
  const metrics: Metric[] = [
    {
      label: "Models",
      value: String(modelsResult.data.length),
      detail: formatDataSource(modelsResult.source),
      tone: "neutral",
    },
    {
      label: "Paper eligible",
      value: String(promotedCount),
      detail: "Simulation-only model promotion state",
      tone: promotedCount > 0 ? "good" : "neutral",
    },
    {
      label: "Archived",
      value: String(archivedCount),
      detail: "Removed from active research selection",
      tone: archivedCount > 0 ? "warn" : "neutral",
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
          <h1 className="mt-2 text-3xl font-semibold">Models</h1>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#eef2f5] text-[#44504b]">
              <tr>
                <th className="px-4 py-3 font-semibold">Model</th>
                <th className="px-4 py-3 font-semibold">Type</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Datasets</th>
                <th className="px-4 py-3 font-semibold">Metrics</th>
                <th className="px-4 py-3 font-semibold">Created</th>
              </tr>
            </thead>
            <tbody>
              {modelsResult.data.map((model) => (
                <tr key={model.model_id} className="border-t border-[#edf0f2]">
                  <td className="px-4 py-3">
                    <p className="font-medium text-[#17201b]">
                      {model.name}
                    </p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {model.version} / {shortId(model.model_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <p>{model.model_type}</p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      {model.algorithm}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <ModelStatusBadge model={model} />
                  </td>
                  <td className="px-4 py-3">
                    <p>{shortId(model.training_dataset_id)}</p>
                    <p className="mt-1 text-xs text-[#6c7671]">
                      validation {shortId(model.validation_dataset_id)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    {formatNumber(Object.keys(model.metrics).length, 0)}
                  </td>
                  <td className="px-4 py-3">
                    {formatDateTime(model.created_at)}
                  </td>
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
 * Render a model status badge.
 *
 * @param props - Status badge props.
 * @returns Status badge element.
 */
function ModelStatusBadge({
  model,
}: {
  model: ModelRegistryEntry;
}): ReactElement {
  const classes =
    model.status === "paper_enabled"
      ? "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]"
      : model.status === "archived"
        ? "border-[#df8b8b] bg-[#fff5f5] text-[#5d1616]"
        : "border-[#e4b06b] bg-[#fff9ed] text-[#5a390b]";
  return (
    <span className={`rounded-md border px-2 py-1 text-xs font-medium ${classes}`}>
      {model.status}
    </span>
  );
}
