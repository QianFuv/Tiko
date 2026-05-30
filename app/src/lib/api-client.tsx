/**
 * API client helpers for the Tiko frontend control surface.
 */

import type { BackendHealthState, HealthResponse } from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

/**
 * Resolve the configured backend API base URL.
 *
 * @returns Backend API base URL without a trailing slash.
 */
export function getApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(
    /\/$/,
    "",
  );
}

/**
 * Fetch backend health without making dashboard rendering depend on it.
 *
 * @returns Backend health state with unavailable status on connection failure.
 */
export async function fetchBackendHealth(): Promise<BackendHealthState> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/api/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });

    if (!response.ok) {
      return {
        status: "unavailable",
        data: null,
        error: `Backend returned HTTP ${response.status}`,
      };
    }

    const data = (await response.json()) as HealthResponse;
    return {
      status: "available",
      data,
      error: null,
    };
  } catch (error) {
    return {
      status: "unavailable",
      data: null,
      error: error instanceof Error ? error.message : "Backend unavailable",
    };
  }
}
