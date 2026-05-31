import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunMarketData } from "@/lib/api-client";
import { formatDateTime, formatNumber, shortId } from "@/lib/format";
import type { Candle, MarketEvent, MarketOrderBook, Metric } from "@/lib/types";

/**
 * Render market replay and read-only market data for a simulation run.
 *
 * @param props - Dynamic route props.
 * @returns Run market page.
 */
export default async function MarketPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}): Promise<ReactElement> {
  const { runId } = await params;
  const data = await fetchRunMarketData(runId);
  const latestCandle = data.candles[data.candles.length - 1] ?? null;
  const metrics: Metric[] = [
    {
      label: "Candles",
      value: String(data.candles.length),
      detail: "Point-in-time market candles",
      tone: "neutral",
    },
    {
      label: "Events",
      value: String(data.events.length),
      detail: "Replay and synthetic market events",
      tone: "good",
    },
    {
      label: "Latest close",
      value: latestCandle === null ? "N/A" : formatNumber(latestCandle.close),
      detail: latestCandle?.symbol ?? data.run.symbols.join(", "),
      tone: "neutral",
    },
    {
      label: "Private methods",
      value: data.symbols.private_methods_allowed ? "Allowed" : "Blocked",
      detail: data.symbols.data_policy,
      tone: data.symbols.private_methods_allowed ? "danger" : "good",
    },
  ];

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <RunNavigation
        run={data.run}
        activeSection="market"
        source={data.source}
      />
      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:px-8">
        <div className="grid gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <CandleTable candles={data.candles} />
          <div className="grid content-start gap-6">
            <OrderBookPanel orderBook={data.orderBook} />
            <MarketEventList events={data.events} />
          </div>
        </div>
      </section>
    </main>
  );
}

/**
 * Render run candles.
 *
 * @param props - Candle table props.
 * @returns Candle table element.
 */
function CandleTable({ candles }: { candles: Candle[] }): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Replay Candles</h2>
        <span className="text-sm text-[#5f6b66]">{candles.length} records</span>
      </div>
      <div className="overflow-hidden rounded-lg border border-[#d8dee4] bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#eef2f5] text-[#44504b]">
            <tr>
              <th className="px-4 py-3 font-semibold">Time</th>
              <th className="px-4 py-3 font-semibold">Symbol</th>
              <th className="px-4 py-3 font-semibold">Open</th>
              <th className="px-4 py-3 font-semibold">High</th>
              <th className="px-4 py-3 font-semibold">Low</th>
              <th className="px-4 py-3 font-semibold">Close</th>
              <th className="px-4 py-3 font-semibold">Volume</th>
            </tr>
          </thead>
          <tbody>
            {candles.map((candle) => (
              <tr
                key={`${candle.symbol}-${candle.as_of}`}
                className="border-t border-[#edf0f2]"
              >
                <td className="px-4 py-3">{formatDateTime(candle.as_of)}</td>
                <td className="px-4 py-3">{candle.symbol}</td>
                <td className="px-4 py-3">{formatNumber(candle.open)}</td>
                <td className="px-4 py-3">{formatNumber(candle.high)}</td>
                <td className="px-4 py-3">{formatNumber(candle.low)}</td>
                <td className="px-4 py-3">{formatNumber(candle.close)}</td>
                <td className="px-4 py-3">{formatNumber(candle.volume)}</td>
              </tr>
            ))}
            {candles.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-[#6c7671]" colSpan={7}>
                  No market candles are available for this run.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Render read-only order book data.
 *
 * @param props - Order book panel props.
 * @returns Order book panel element.
 */
function OrderBookPanel({
  orderBook,
}: {
  orderBook: MarketOrderBook;
}): ReactElement {
  const metadata = [
    {
      label: "As of",
      value: orderBook.as_of === null ? "N/A" : formatDateTime(orderBook.as_of),
    },
    {
      label: "Mid",
      value:
        orderBook.mid_price === null
          ? "N/A"
          : formatNumber(orderBook.mid_price),
    },
    {
      label: "Spread",
      value:
        orderBook.spread_bps === null
          ? "N/A"
          : `${formatNumber(orderBook.spread_bps)} bps`,
    },
    {
      label: "Depth 1%",
      value:
        orderBook.depth_1pct_usd === null
          ? "N/A"
          : formatNumber(orderBook.depth_1pct_usd),
    },
    {
      label: "Source",
      value: orderBook.source ?? "N/A",
    },
  ];

  return (
    <div>
      <h2 className="text-xl font-semibold">Order Book</h2>
      <div className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-5">
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="font-medium text-[#17201b]">{orderBook.symbol}</span>
          <span className="break-words text-right text-[#5f6b66]">
            {orderBook.data_policy}
          </span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {metadata.map((item) => (
            <div key={item.label} className="border-b border-[#edf0f2] pb-2">
              <p className="text-xs font-medium uppercase text-[#6c7671]">
                {item.label}
              </p>
              <p className="mt-1 text-sm font-semibold text-[#17201b]">
                {item.value}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <BookSide title="Bids" rows={orderBook.bids} />
          <BookSide title="Asks" rows={orderBook.asks} />
        </div>
      </div>
    </div>
  );
}

/**
 * Render one side of an order book.
 *
 * @param props - Book side props.
 * @returns Book side element.
 */
function BookSide({
  title,
  rows,
}: {
  title: string;
  rows: [string, string][];
}): ReactElement {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <dl className="mt-2 grid gap-2 text-sm">
        {rows.map(([price, quantity]) => (
          <div
            key={`${price}-${quantity}`}
            className="flex items-center justify-between gap-3 border-b border-[#edf0f2] pb-2"
          >
            <dt className="text-[#5f6b66]">{formatNumber(price)}</dt>
            <dd className="font-medium text-[#17201b]">
              {formatNumber(quantity, 6)}
            </dd>
          </div>
        ))}
        {rows.length === 0 ? (
          <p className="text-sm text-[#5f6b66]">No depth available.</p>
        ) : null}
      </dl>
    </div>
  );
}

/**
 * Render market events.
 *
 * @param props - Market event list props.
 * @returns Market event list element.
 */
function MarketEventList({ events }: { events: MarketEvent[] }): ReactElement {
  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Market Events</h2>
        <span className="text-sm text-[#5f6b66]">{events.length} records</span>
      </div>
      <div className="grid gap-3">
        {events.map((event) => (
          <article
            key={event.event_id}
            className="rounded-lg border border-[#d8dee4] bg-white p-4"
          >
            <p className="text-sm text-[#5f6b66]">
              {shortId(event.event_id)} / {formatDateTime(event.simulated_time)}
            </p>
            <h3 className="mt-2 text-base font-semibold">
              {event.type} {event.symbol === null ? "" : `/ ${event.symbol}`}
            </h3>
            <p className="mt-2 text-sm leading-6 text-[#44504b]">
              {formatRecord(event.payload)}
            </p>
          </article>
        ))}
        {events.length === 0 ? (
          <div className="rounded-lg border border-[#d8dee4] bg-white p-5 text-sm text-[#5f6b66]">
            No market events are available for this run.
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Format a record for compact display.
 *
 * @param record - Record to format.
 * @returns Compact display string.
 */
function formatRecord(record: Record<string, unknown>): string {
  return Object.entries(record)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" / ");
}
