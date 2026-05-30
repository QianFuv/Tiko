/**
 * Shared frontend types for Tiko API responses and dashboard state.
 */

export type HealthResponse = {
  status: string;
  safety_mode: string;
  private_exchange_methods_allowed: boolean;
  trading_credentials_allowed: boolean;
};

export type BackendHealthState = {
  status: "available" | "unavailable";
  data: HealthResponse | null;
  error: string | null;
};

export type Metric = {
  label: string;
  value: string;
  detail: string;
};

export type RuntimePanel = {
  title: string;
  value: string;
  detail: string;
  tone: "neutral" | "good" | "warn";
};
