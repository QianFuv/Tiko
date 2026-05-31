/**
 * Shared run navigation for simulation observation pages.
 */

import Link from "next/link";
import type { ReactElement } from "react";

import { formatDataSource } from "@/lib/format";
import type { DataSource, SimulationRun } from "@/lib/types";

type RunSection = {
  key: string;
  label: string;
  href: string;
};

/**
 * Build run section navigation metadata.
 *
 * @param runId - Simulation run identifier.
 * @returns Run navigation sections.
 */
function buildRunSections(runId: string): RunSection[] {
  return [
    {
      key: "dashboard",
      label: "Dashboard",
      href: `/simulations/${runId}/dashboard`,
    },
    {
      key: "decisions",
      label: "Decisions",
      href: `/simulations/${runId}/decisions`,
    },
    {
      key: "agent-trace",
      label: "Agent Trace",
      href: `/simulations/${runId}/agent-trace`,
    },
    {
      key: "orders",
      label: "Orders",
      href: `/simulations/${runId}/orders`,
    },
    {
      key: "portfolio",
      label: "Portfolio",
      href: `/simulations/${runId}/portfolio`,
    },
    {
      key: "risk",
      label: "Risk",
      href: `/simulations/${runId}/risk`,
    },
    {
      key: "review",
      label: "Review",
      href: `/simulations/${runId}/review`,
    },
    {
      key: "reports",
      label: "Reports",
      href: `/simulations/${runId}/reports`,
    },
  ];
}

/**
 * Render shared run header and route navigation.
 *
 * @param props - Run navigation props.
 * @returns Run navigation element.
 */
export function RunNavigation({
  run,
  activeSection,
  source,
}: {
  run: SimulationRun;
  activeSection: string;
  source: DataSource;
}): ReactElement {
  const sections = buildRunSections(run.run_id);
  return (
    <header className="border-b border-[#d8dee4] bg-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-5 lg:px-8">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <Link
              href="/simulations"
              className="text-sm font-medium text-[#1f6f8b] hover:text-[#164e63]"
            >
              Simulations
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-[#17201b]">
              {run.name}
            </h1>
            <p className="mt-1 text-sm text-[#5f6b66]">
              {run.status} / {run.mode} / {run.symbols.join(", ")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <span className="rounded-md border border-[#d8dee4] bg-[#f7f9fa] px-3 py-1 text-[#44504b]">
              {formatDataSource(source)}
            </span>
            <span className="rounded-md border border-[#9bc5ae] bg-[#f4fbf6] px-3 py-1 text-[#173f2a]">
              Simulation only
            </span>
          </div>
        </div>
        <nav className="flex gap-2 overflow-x-auto">
          {sections.map((section) => {
            const isActive = section.key === activeSection;
            return (
              <Link
                key={section.key}
                href={section.href}
                className={`rounded-md border px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "border-[#1f6f8b] bg-[#e8f4f8] text-[#17485b]"
                    : "border-[#d8dee4] bg-white text-[#44504b] hover:border-[#9db4bd]"
                }`}
              >
                {section.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
