/**
 * Metric display component for operational dashboard values.
 */

import type { ReactElement } from "react";

import type { Metric } from "@/lib/types";

const toneClasses = {
  neutral: "border-[#d8dee4] bg-white text-[#17201b]",
  good: "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]",
  warn: "border-[#e4b06b] bg-[#fff9ed] text-[#5a390b]",
  danger: "border-[#df8b8b] bg-[#fff5f5] text-[#5d1616]",
};

/**
 * Render a compact metric card.
 *
 * @param props - Metric card props.
 * @returns Metric card element.
 */
export function MetricCard({ metric }: { metric: Metric }): ReactElement {
  const tone = metric.tone ?? "neutral";
  return (
    <article className={`rounded-lg border p-4 ${toneClasses[tone]}`}>
      <p className="text-sm font-medium text-[#5f6b66]">{metric.label}</p>
      <p className="mt-2 text-2xl font-semibold text-[#17201b]">
        {metric.value}
      </p>
      <p className="mt-2 text-sm leading-6 text-[#5f6b66]">{metric.detail}</p>
    </article>
  );
}
