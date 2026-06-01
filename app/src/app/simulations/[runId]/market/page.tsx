import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { RunNavigation } from "@/components/layout/RunNavigation";
import { MetricCard } from "@/components/metric/MetricCard";
import { fetchRunMarketData, getApiBaseUrl } from "@/lib/api-client";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/format";
import type {
  Candle,
  Fill,
  MarketEvent,
  MarketOrderBook,
  Metric,
  SimOrder,
} from "@/lib/types";

type ReplayCommand = "start" | "pause" | "resume" | "stop" | "step" | "speed";

type MarketEventType =
  | "news_event"
  | "liquidity_shock"
  | "volatility_shock"
  | "funding_update"
  | "system_event";

type ExecutionPriceRange = {
  low: number;
  high: number;
};

const REPLAY_COMMANDS: ReplayCommand[] = ["start", "pause", "resume", "stop"];
const EXECUTION_CANDLE_LIMIT = 8;
const EXECUTION_FILL_LIMIT = 6;
const MARKET_EVENT_TYPES: MarketEventType[] = [
  "news_event",
  "liquidity_shock",
  "volatility_shock",
  "funding_update",
  "system_event",
];

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

        <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <ReplayControlsPanel runId={runId} />
          <EventInjectionPanel runId={runId} symbols={data.run.symbols} />
        </div>

        <MarketExecutionTape
          candles={data.candles}
          fills={data.fills}
          orders={data.orders}
        />

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
 * Render replay lifecycle controls.
 *
 * @param props - Replay control props.
 * @returns Replay control panel.
 */
function ReplayControlsPanel({ runId }: { runId: string }): ReactElement {
  return (
    <section>
      <h2 className="text-xl font-semibold">Replay Controls</h2>
      <div className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5">
        <div className="grid gap-2 sm:grid-cols-4">
          {REPLAY_COMMANDS.map((command) => (
            <form key={command} action={submitReplayCommand}>
              <input name="run_id" type="hidden" value={runId} />
              <input name="command" type="hidden" value={command} />
              <button
                type="submit"
                className="w-full rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-semibold text-[#17201b] hover:border-[#1f6f8b] hover:text-[#1f6f8b]"
              >
                {formatCommandLabel(command)}
              </button>
            </form>
          ))}
        </div>
        <form
          action={submitReplayCommand}
          className="grid gap-3 border-t border-[#edf0f2] pt-4 sm:grid-cols-[1fr_auto]"
        >
          <input name="run_id" type="hidden" value={runId} />
          <input name="command" type="hidden" value="step" />
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Step confidence
            <input
              name="confidence"
              type="number"
              min="0"
              max="1"
              step="0.01"
              defaultValue="0.7"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              className="w-full rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63] sm:w-auto"
            >
              Step
            </button>
          </div>
        </form>
        <form
          action={submitReplayCommand}
          className="grid gap-3 border-t border-[#edf0f2] pt-4 sm:grid-cols-[1fr_auto]"
        >
          <input name="run_id" type="hidden" value={runId} />
          <input name="command" type="hidden" value="speed" />
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Speed multiplier
            <input
              name="speed_multiplier"
              type="number"
              min="0.1"
              step="0.1"
              defaultValue="1"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              className="w-full rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63] sm:w-auto"
            >
              Set Speed
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

/**
 * Render manual simulated market event injection controls.
 *
 * @param props - Event injection props.
 * @returns Event injection panel.
 */
function EventInjectionPanel({
  runId,
  symbols,
}: {
  runId: string;
  symbols: string[];
}): ReactElement {
  return (
    <section>
      <h2 className="text-xl font-semibold">Event Injection</h2>
      <form
        action={injectMarketEvent}
        className="mt-3 grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5"
      >
        <input name="run_id" type="hidden" value={runId} />
        <div className="grid gap-3 md:grid-cols-3">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Event type
            <select
              name="type"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              {MARKET_EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Symbol
            <select
              name="symbol"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              <option value="">Run-wide</option>
              {symbols.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Confidence
            <input
              name="confidence"
              type="number"
              min="0"
              max="1"
              step="0.01"
              defaultValue="0.9"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_10rem]">
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Headline
            <input
              name="headline"
              required
              minLength={1}
              defaultValue="Mock volatility shock"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Severity
            <select
              name="severity"
              defaultValue="medium"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
        </div>
        <label className="grid gap-2 text-sm font-medium text-[#17201b]">
          Sentiment
          <input
            name="sentiment"
            type="number"
            min="-1"
            max="1"
            step="0.1"
            defaultValue="0"
            className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
          />
        </label>
        <div className="flex justify-end">
          <button
            type="submit"
            className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
          >
            Inject Event
          </button>
        </div>
      </form>
    </section>
  );
}

/**
 * Render recent candles with simulated execution markers.
 *
 * @param props - Execution tape props.
 * @returns Market execution tape element.
 */
function MarketExecutionTape({
  candles,
  fills,
  orders,
}: {
  candles: Candle[];
  fills: Fill[];
  orders: SimOrder[];
}): ReactElement {
  const recentCandles = candles.slice(-EXECUTION_CANDLE_LIMIT);
  const recentFills = fills.slice(-EXECUTION_FILL_LIMIT);
  const priceRange = buildExecutionPriceRange(recentCandles, recentFills);
  const markerMap = buildFillMarkerMap(recentCandles, recentFills);

  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-xl font-semibold">Execution Markers</h2>
        <span className="text-sm text-[#5f6b66]">
          {recentFills.length} recent fills
        </span>
      </div>
      <div className="grid gap-4 rounded-lg border border-[#d8dee4] bg-white p-5 lg:grid-cols-[1.2fr_0.8fr]">
        {recentCandles.length === 0 ? (
          <div className="text-sm text-[#5f6b66]">
            No candles are available for execution markers.
          </div>
        ) : (
          <div className="min-w-0">
            <div className="flex h-56 items-stretch gap-3 overflow-x-auto pb-2">
              {recentCandles.map((candle) => (
                <CandleMarkerColumn
                  key={`${candle.symbol}-${candle.as_of}`}
                  candle={candle}
                  fills={markerMap.get(buildCandleMarkerKey(candle)) ?? []}
                  priceRange={priceRange}
                />
              ))}
            </div>
            <div className="mt-2 flex items-center justify-between gap-3 text-xs text-[#6c7671]">
              <span>{formatNumber(priceRange.low)}</span>
              <span>{formatNumber(priceRange.high)}</span>
            </div>
          </div>
        )}

        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[#17201b]">Fill Details</h3>
          <div className="mt-3 grid gap-3">
            {recentFills.map((fill) => (
              <FillMarkerDetail
                key={fill.fill_id}
                fill={fill}
                order={orders.find((order) => order.order_id === fill.order_id)}
              />
            ))}
            {recentFills.length === 0 ? (
              <div className="rounded-md border border-[#edf0f2] p-3 text-sm text-[#5f6b66]">
                No fills are available for this run.
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * Render one candle column with attached fill markers.
 *
 * @param props - Candle marker column props.
 * @returns Candle marker column element.
 */
function CandleMarkerColumn({
  candle,
  fills,
  priceRange,
}: {
  candle: Candle;
  fills: Fill[];
  priceRange: ExecutionPriceRange;
}): ReactElement {
  const highTop = priceToTopPercent(candle.high, priceRange);
  const lowTop = priceToTopPercent(candle.low, priceRange);
  const openTop = priceToTopPercent(candle.open, priceRange);
  const closeTop = priceToTopPercent(candle.close, priceRange);
  const bodyTop = Math.min(openTop, closeTop);
  const bodyHeight = Math.max(Math.abs(openTop - closeTop), 3);
  const wickHeight = Math.max(lowTop - highTop, 6);

  return (
    <div className="grid min-w-24 flex-1 content-between gap-2 text-center">
      <div className="relative h-40 rounded-md bg-[#f7f9fa]">
        <span
          className="absolute left-1/2 w-px -translate-x-1/2 rounded-full bg-[#7b8790]"
          style={{ height: `${wickHeight}%`, top: `${highTop}%` }}
        />
        <span
          className="absolute left-1/2 w-5 -translate-x-1/2 rounded-sm border border-[#1f6f8b] bg-[#cfe8ef]"
          style={{ height: `${bodyHeight}%`, top: `${bodyTop}%` }}
        />
        <span
          className="absolute left-[calc(50%-1rem)] h-px w-4 bg-[#17201b]"
          style={{ top: `${openTop}%` }}
        />
        <span
          className="absolute left-1/2 h-px w-4 bg-[#17201b]"
          style={{ top: `${closeTop}%` }}
        />
        {fills.map((fill, index) => (
          <span
            key={fill.fill_id}
            className={`absolute h-3 w-3 rounded-full ring-2 ring-white ${fillMarkerClass(fill)}`}
            style={{
              left: `${markerLeftPercent(index)}%`,
              top: `${priceToTopPercent(fill.price, priceRange)}%`,
              transform: "translate(-50%, -50%)",
            }}
            title={`${fill.side} ${fill.symbol} ${formatCurrency(fill.price)}`}
          />
        ))}
      </div>
      <div className="min-w-0 text-xs">
        <p className="truncate font-medium text-[#17201b]">{candle.symbol}</p>
        <p className="text-[#6c7671]">{formatDateTime(candle.as_of)}</p>
      </div>
    </div>
  );
}

/**
 * Render one fill marker detail row.
 *
 * @param props - Fill marker detail props.
 * @returns Fill marker detail element.
 */
function FillMarkerDetail({
  fill,
  order,
}: {
  fill: Fill;
  order: SimOrder | undefined;
}): ReactElement {
  return (
    <article className="rounded-md border border-[#edf0f2] p-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-[#17201b]">
            {fill.side} {fill.symbol}
          </p>
          <p className="mt-1 text-[#5f6b66]">
            {formatDateTime(fill.filled_at_sim_time)}
          </p>
        </div>
        <span
          className={`mt-1 h-3 w-3 shrink-0 rounded-full ${fillMarkerClass(fill)}`}
        />
      </div>
      <dl className="mt-3 grid gap-2">
        <ExecutionDetail label="Price" value={formatCurrency(fill.price)} />
        <ExecutionDetail
          label="Quantity"
          value={formatNumber(fill.quantity, 6)}
        />
        <ExecutionDetail label="Fee" value={formatCurrency(fill.fee)} />
        <ExecutionDetail
          label="Order"
          value={order === undefined ? shortId(fill.order_id) : order.status}
        />
      </dl>
    </article>
  );
}

/**
 * Render one execution detail row.
 *
 * @param props - Execution detail props.
 * @returns Execution detail element.
 */
function ExecutionDetail({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[#6c7671]">{label}</dt>
      <dd className="break-words text-right font-medium text-[#17201b]">
        {value}
      </dd>
    </div>
  );
}

/**
 * Build a price range for execution marker placement.
 *
 * @param candles - Recent candles.
 * @param fills - Recent fills.
 * @returns Bounded price range.
 */
function buildExecutionPriceRange(
  candles: Candle[],
  fills: Fill[],
): ExecutionPriceRange {
  const prices = [
    ...candles.flatMap((candle) => [
      candle.open,
      candle.high,
      candle.low,
      candle.close,
    ]),
    ...fills.map((fill) => fill.price),
  ]
    .map(parseMarketNumber)
    .filter((price) => Number.isFinite(price));

  if (prices.length === 0) {
    return { low: 0, high: 1 };
  }

  const low = Math.min(...prices);
  const high = Math.max(...prices);
  if (low === high) {
    const padding = Math.max(Math.abs(low) * 0.01, 1);
    return { low: low - padding, high: high + padding };
  }
  return { low, high };
}

/**
 * Group fills by the candle used for marker placement.
 *
 * @param candles - Recent candles.
 * @param fills - Recent fills.
 * @returns Map of candle keys to fills.
 */
function buildFillMarkerMap(
  candles: Candle[],
  fills: Fill[],
): Map<string, Fill[]> {
  const markerMap = new Map<string, Fill[]>();
  fills.forEach((fill) => {
    const candle = findMarkerCandle(candles, fill);
    if (candle === null) {
      return;
    }
    const key = buildCandleMarkerKey(candle);
    markerMap.set(key, [...(markerMap.get(key) ?? []), fill]);
  });
  return markerMap;
}

/**
 * Find the candle that should host one fill marker.
 *
 * @param candles - Candidate candles.
 * @param fill - Fill to place.
 * @returns Matching candle or null.
 */
function findMarkerCandle(candles: Candle[], fill: Fill): Candle | null {
  const sameSymbolCandles = candles.filter(
    (candle) => candle.symbol === fill.symbol,
  );
  if (sameSymbolCandles.length === 0) {
    return null;
  }
  const fillTime = parseMarketTime(fill.filled_at_sim_time);
  const matchingCandle = sameSymbolCandles.find(
    (candle) => parseMarketTime(candle.as_of) >= fillTime,
  );
  return (
    matchingCandle ?? sameSymbolCandles[sameSymbolCandles.length - 1] ?? null
  );
}

/**
 * Build a stable marker key for a candle.
 *
 * @param candle - Candle record.
 * @returns Marker key.
 */
function buildCandleMarkerKey(candle: Candle): string {
  return `${candle.symbol}-${candle.as_of}`;
}

/**
 * Convert a price to a vertical top percentage.
 *
 * @param value - Decimal price value.
 * @param range - Price range.
 * @returns CSS top percentage.
 */
function priceToTopPercent(
  value: string | number,
  range: ExecutionPriceRange,
): number {
  const price = parseMarketNumber(value);
  const span = range.high - range.low;
  if (span <= 0) {
    return 50;
  }
  return clampPercent(100 - ((price - range.low) / span) * 100);
}

/**
 * Return a horizontal marker offset for multiple fills on one candle.
 *
 * @param index - Marker index.
 * @returns CSS left percentage.
 */
function markerLeftPercent(index: number): number {
  return Math.min(68, 46 + index * 12);
}

/**
 * Return a fill marker CSS class.
 *
 * @param fill - Fill record.
 * @returns Fill marker class.
 */
function fillMarkerClass(fill: Fill): string {
  return fill.side === "buy" ? "bg-[#228452]" : "bg-[#b42318]";
}

/**
 * Clamp a percent into the visible tape range.
 *
 * @param value - Percent value.
 * @returns Clamped percent.
 */
function clampPercent(value: number): number {
  return Math.min(96, Math.max(4, value));
}

/**
 * Parse a market decimal for display calculations.
 *
 * @param value - Decimal-like value.
 * @returns Parsed number.
 */
function parseMarketNumber(value: string | number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Parse a market timestamp for marker matching.
 *
 * @param value - Timestamp value.
 * @returns Milliseconds since epoch or zero.
 */
function parseMarketTime(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
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

/**
 * Submit a simulation replay command to the backend control plane.
 *
 * @param formData - Submitted replay command fields.
 */
async function submitReplayCommand(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  const command = readReplayCommand(formData);
  if (command === "step") {
    await postBackendJson(`/api/simulations/${runId}/step`, {
      confidence: readBoundedNumber(formData, "confidence", 0, 1),
    });
  } else if (command === "speed") {
    await postBackendJson(`/api/simulations/${runId}/speed`, {
      speed_multiplier: readPositiveNumberString(formData, "speed_multiplier"),
    });
  } else {
    await postBackendJson(`/api/simulations/${runId}/${command}`, null);
  }
  refreshMarketPage(runId);
}

/**
 * Submit a controlled simulated market event to the backend.
 *
 * @param formData - Submitted event injection fields.
 */
async function injectMarketEvent(formData: FormData): Promise<void> {
  "use server";

  const runId = readRequiredFormValue(formData, "run_id");
  await postBackendJson("/api/market/events/inject", {
    run_id: runId,
    type: readMarketEventType(formData),
    symbol: readOptionalFormValue(formData, "symbol"),
    payload: {
      headline: readRequiredFormValue(formData, "headline"),
      severity: readRequiredFormValue(formData, "severity"),
      sentiment: readBoundedNumber(formData, "sentiment", -1, 1),
    },
    source: "manual",
    confidence: readBoundedNumber(formData, "confidence", 0, 1),
  });
  refreshMarketPage(runId);
}

/**
 * Post a JSON mutation to the backend with operator credentials.
 *
 * @param path - Backend API path.
 * @param payload - Optional JSON payload.
 */
async function postBackendJson(
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
      `Market control failed: ${await readErrorDetail(response)}`,
    );
  }
}

/**
 * Build frontend operator headers for backend control-plane mutations.
 *
 * @returns Operator request headers.
 */
function getOperatorHeaders(): Record<string, string> {
  return {
    "X-Tiko-Role": "operator",
    "X-Tiko-User": "frontend@app.local",
  };
}

/**
 * Revalidate and redirect back to the market page.
 *
 * @param runId - Simulation run identifier.
 */
function refreshMarketPage(runId: string): never {
  const path = `/simulations/${runId}/market`;
  revalidatePath(path);
  redirect(path);
}

/**
 * Read a replay command from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid replay command.
 */
function readReplayCommand(formData: FormData): ReplayCommand {
  const command = readRequiredFormValue(formData, "command");
  if (isReplayCommand(command)) {
    return command;
  }
  throw new Error("command is invalid.");
}

/**
 * Read a market event type from form data.
 *
 * @param formData - Submitted form data.
 * @returns Valid market event type.
 */
function readMarketEventType(formData: FormData): MarketEventType {
  const type = readRequiredFormValue(formData, "type");
  if (isMarketEventType(type)) {
    return type;
  }
  throw new Error("type is invalid.");
}

/**
 * Read a bounded numeric field from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @param minimum - Inclusive minimum value.
 * @param maximum - Inclusive maximum value.
 * @returns Parsed number.
 */
function readBoundedNumber(
  formData: FormData,
  key: string,
  minimum: number,
  maximum: number,
): number {
  const value = Number(readRequiredFormValue(formData, key));
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${key} is invalid.`);
  }
  return value;
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
 * Read an optional string field from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Trimmed value or null.
 */
function readOptionalFormValue(formData: FormData, key: string): string | null {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  return value.trim();
}

/**
 * Return whether a string is a replay command.
 *
 * @param command - Candidate replay command.
 * @returns Whether the command is supported.
 */
function isReplayCommand(command: string): command is ReplayCommand {
  return (
    command === "step" ||
    command === "speed" ||
    (REPLAY_COMMANDS as readonly string[]).includes(command)
  );
}

/**
 * Return whether a string is a market event type.
 *
 * @param type - Candidate event type.
 * @returns Whether the type is supported.
 */
function isMarketEventType(type: string): type is MarketEventType {
  return (MARKET_EVENT_TYPES as readonly string[]).includes(type);
}

/**
 * Format a replay command for display.
 *
 * @param command - Replay command.
 * @returns Display label.
 */
function formatCommandLabel(command: ReplayCommand): string {
  return command.charAt(0).toUpperCase() + command.slice(1);
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
