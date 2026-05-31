/**
 * Display formatting helpers for the Tiko dashboard.
 */

/**
 * Format a decimal value as a compact number.
 *
 * @param value - Decimal string or number.
 * @param maximumFractionDigits - Maximum decimal digits.
 * @returns Formatted number.
 */
export function formatNumber(
  value: string | number,
  maximumFractionDigits = 2,
): string {
  const parsed = parseDisplayNumber(value);
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
  }).format(parsed);
}

/**
 * Format a decimal value as a currency-like amount.
 *
 * @param value - Decimal string or number.
 * @param currency - Display currency suffix.
 * @returns Formatted amount.
 */
export function formatCurrency(
  value: string | number,
  currency = "USDT",
): string {
  return `${formatNumber(value, 2)} ${currency}`;
}

/**
 * Format a decimal ratio as a percentage.
 *
 * @param value - Decimal string or number.
 * @returns Formatted percentage.
 */
export function formatPercent(value: string | number): string {
  return `${formatNumber(parseDisplayNumber(value) * 100, 2)}%`;
}

/**
 * Format a timestamp for dashboard tables.
 *
 * @param value - ISO-like timestamp.
 * @returns Human-readable timestamp.
 */
export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/**
 * Shorten a UUID-like identifier.
 *
 * @param value - Full identifier.
 * @returns Short identifier.
 */
export function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}...` : value;
}

/**
 * Format backend/demo source labels.
 *
 * @param value - Data source marker.
 * @returns Display label.
 */
export function formatDataSource(value: string): string {
  if (value === "backend") {
    return "Live API";
  }
  if (value === "mixed") {
    return "Mixed";
  }
  return "Demo fallback";
}

/**
 * Parse a display number with a safe fallback.
 *
 * @param value - Decimal string or number.
 * @returns Parsed number.
 */
function parseDisplayNumber(value: string | number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
