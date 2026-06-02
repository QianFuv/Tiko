import Link from "next/link";
import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { fetchRunDashboardData } from "@/lib/api-client";
import { formatDateTime, formatPercent, shortId } from "@/lib/format";

const DECISIONS_PAGE_SIZE = 25;

type SearchParams = Record<string, string | string[] | undefined>;

type PageSlice<Item> = {
  items: Item[];
  currentPage: number;
  pageCount: number;
  totalItems: number;
  startItem: number;
  endItem: number;
};

/**
 * Render the decision trace page for a simulation run.
 *
 * @param props - Dynamic route props.
 * @returns Decision trace page.
 */
export default async function DecisionsPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<SearchParams>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const resolvedSearchParams = await searchParams;
  const data = await fetchRunDashboardData(runId);
  const decisionPage = readPageParam(resolvedSearchParams, "decisionsPage");
  const decisionPageSlice = paginateItems(
    data.decisions,
    decisionPage,
    DECISIONS_PAGE_SIZE,
  );

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="decisions"
        source={data.source}
      />
      <section className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-xl font-semibold">Decision Trace</h2>
            <p className="mt-1 text-sm text-[#5f6b66]">
              Structured trade intents and risk-adjacent evidence.
            </p>
          </div>
          <span className="text-sm text-[#5f6b66]">
            {data.decisions.length} records
          </span>
        </div>

        <div className="grid gap-4">
          {decisionPageSlice.items.map((decision) => (
            <article
              key={decision.decision_id}
              className="rounded-lg border border-[#d8dee4] bg-white p-5"
            >
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-sm text-[#5f6b66]">
                    {shortId(decision.decision_id)} / {decision.agent_id}
                  </p>
                  <h3 className="mt-2 text-lg font-semibold">
                    {decision.symbol} {decision.action}
                  </h3>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-[#44504b]">
                    {decision.thesis}
                  </p>
                </div>
                <div className="grid min-w-56 gap-2 text-sm">
                  <TraceMetric
                    label="Confidence"
                    value={formatPercent(decision.confidence)}
                  />
                  <TraceMetric
                    label="Data quality"
                    value={formatPercent(decision.data_quality_score)}
                  />
                  <TraceMetric
                    label="Target weight"
                    value={formatPercent(decision.target_weight)}
                  />
                  <TraceMetric
                    label="Created"
                    value={formatDateTime(decision.created_at_sim_time)}
                  />
                </div>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <TraceList
                  title="Evidence"
                  values={decision.evidence.map((item) =>
                    Object.entries(item)
                      .map(([key, value]) => `${key}: ${String(value)}`)
                      .join(" / "),
                  )}
                />
                <TraceList
                  title="Invalidation"
                  values={decision.invalidation_conditions}
                />
              </div>
            </article>
          ))}
          {data.decisions.length === 0 ? (
            <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
              No decisions recorded for this run.
            </div>
          ) : null}
        </div>
        <PaginationControls
          pageSlice={decisionPageSlice}
          previousHref={buildDecisionsPageHref(
            runId,
            decisionPageSlice.currentPage - 1,
          )}
          nextHref={buildDecisionsPageHref(
            runId,
            decisionPageSlice.currentPage + 1,
          )}
        />
      </section>
    </main>
  );
}

/**
 * Render previous and next controls for decision cards.
 *
 * @param props - Pagination control props.
 * @returns Pagination controls.
 */
function PaginationControls<Item>({
  pageSlice,
  previousHref,
  nextHref,
}: {
  pageSlice: PageSlice<Item>;
  previousHref: string;
  nextHref: string;
}): ReactElement {
  const isPreviousDisabled =
    pageSlice.totalItems === 0 || pageSlice.currentPage <= 1;
  const isNextDisabled =
    pageSlice.totalItems === 0 || pageSlice.currentPage >= pageSlice.pageCount;

  return (
    <div className="mt-4 flex flex-col gap-3 rounded-lg border border-[#d8dee4] bg-white px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
      <p className="text-[#5f6b66]">{formatPaginationRange(pageSlice)}</p>
      <div className="flex items-center gap-2">
        <span className="text-[#5f6b66]">
          Page {pageSlice.currentPage} of {pageSlice.pageCount}
        </span>
        <PaginationLink
          href={previousHref}
          label="Decisions previous"
          text="Previous"
          disabled={isPreviousDisabled}
        />
        <PaginationLink
          href={nextHref}
          label="Decisions next"
          text="Next"
          disabled={isNextDisabled}
        />
      </div>
    </div>
  );
}

/**
 * Render one pagination link or disabled placeholder.
 *
 * @param props - Pagination link props.
 * @returns Pagination link element.
 */
function PaginationLink({
  href,
  label,
  text,
  disabled,
}: {
  href: string;
  label: string;
  text: string;
  disabled: boolean;
}): ReactElement {
  const className =
    "inline-flex min-w-20 items-center justify-center rounded-md border px-3 py-1.5 text-xs font-semibold";

  if (disabled) {
    return (
      <span
        aria-disabled="true"
        aria-label={label}
        className={`${className} cursor-not-allowed border-[#d8dee4] text-[#9aa3a0]`}
      >
        {text}
      </span>
    );
  }

  return (
    <Link
      aria-label={label}
      className={`${className} border-[#b7c2c8] text-[#24342d] hover:bg-[#eef2f5]`}
      href={href}
    >
      {text}
    </Link>
  );
}

/**
 * Return a bounded page slice for a list.
 *
 * @param items - Source items.
 * @param requestedPage - Requested one-based page number.
 * @param pageSize - Maximum items per page.
 * @returns Bounded page slice metadata and items.
 */
function paginateItems<Item>(
  items: Item[],
  requestedPage: number,
  pageSize: number,
): PageSlice<Item> {
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(Math.max(requestedPage, 1), pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const pageItems = items.slice(startIndex, startIndex + pageSize);

  return {
    items: pageItems,
    currentPage,
    pageCount,
    totalItems: items.length,
    startItem: items.length === 0 ? 0 : startIndex + 1,
    endItem: Math.min(startIndex + pageItems.length, items.length),
  };
}

/**
 * Read a positive page number from URL search params.
 *
 * @param searchParams - Resolved URL search params.
 * @param key - Query parameter key.
 * @returns Positive page number, defaulting to 1.
 */
function readPageParam(searchParams: SearchParams, key: string): number {
  const value = searchParams[key];
  const rawValue = Array.isArray(value) ? value[0] : value;
  if (rawValue === undefined) {
    return 1;
  }
  const parsedValue = Number(rawValue);
  return Number.isInteger(parsedValue) && parsedValue > 0 ? parsedValue : 1;
}

/**
 * Build a decisions page href for one page.
 *
 * @param runId - Simulation run identifier.
 * @param decisionsPage - Decision page number.
 * @returns Decisions page href.
 */
function buildDecisionsPageHref(runId: string, decisionsPage: number): string {
  if (decisionsPage <= 1) {
    return `/simulations/${runId}/decisions`;
  }
  const params = new URLSearchParams({ decisionsPage: String(decisionsPage) });
  return `/simulations/${runId}/decisions?${params.toString()}`;
}

/**
 * Format the visible decision range for one page.
 *
 * @param pageSlice - Current page slice metadata.
 * @returns Human-readable decision range.
 */
function formatPaginationRange<Item>(pageSlice: PageSlice<Item>): string {
  if (pageSlice.totalItems === 0) {
    return "No decisions to display";
  }
  return `Showing ${pageSlice.startItem}-${pageSlice.endItem} of ${pageSlice.totalItems} decisions`;
}

/**
 * Render one trace metric row.
 *
 * @param props - Trace metric props.
 * @returns Trace metric row.
 */
function TraceMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#edf0f2] pb-2">
      <span className="text-[#5f6b66]">{label}</span>
      <span className="font-medium text-[#17201b]">{value}</span>
    </div>
  );
}

/**
 * Render a compact trace list.
 *
 * @param props - Trace list props.
 * @returns Trace list element.
 */
function TraceList({
  title,
  values,
}: {
  title: string;
  values: string[];
}): ReactElement {
  return (
    <div className="border-t border-[#edf0f2] pt-4">
      <h4 className="text-sm font-semibold text-[#17201b]">{title}</h4>
      <ul className="mt-2 grid gap-2 text-sm leading-6 text-[#44504b]">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}
