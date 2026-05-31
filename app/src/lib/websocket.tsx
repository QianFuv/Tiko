/**
 * Realtime WebSocket helpers for simulation observation.
 */

export const SIMULATION_STREAM_TOPICS = [
  "market.candle",
  "agent.run",
  "decision.created",
  "risk.reviewed",
  "order.updated",
  "fill.created",
  "portfolio.updated",
  "alert.created",
  "simulation.status",
  "simulation.heartbeat",
] as const;

export type SimulationStreamTopic = (typeof SIMULATION_STREAM_TOPICS)[number];

export type SimulationSubscriptionPayload = {
  type: "subscribe";
  topics: SimulationStreamTopic[];
  live?: boolean;
};

export type SimulationStreamEvent = {
  event_id: string;
  topic: SimulationStreamTopic;
  run_id: string;
  simulated_time: string;
  payload: Record<string, unknown>;
};

export type SimulationStreamState = {
  runId: string;
  lastEvent: SimulationStreamEvent | null;
  eventCount: number;
  countsByTopic: Partial<Record<SimulationStreamTopic, number>>;
};

/**
 * Build the WebSocket URL for a simulation stream.
 *
 * @param apiBaseUrl - HTTP API base URL.
 * @param runId - Simulation run identifier.
 * @returns WebSocket URL for the run stream.
 */
export function buildSimulationWebSocketUrl(
  apiBaseUrl: string,
  runId: string,
): string {
  const url = new URL(apiBaseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/simulations/${runId}`;
  url.search = "";
  return url.toString();
}

/**
 * Build the standard simulation stream subscription payload.
 *
 * @param topics - Optional topics to subscribe to.
 * @param live - Whether the backend should keep streaming live fanout events.
 * @returns Subscription payload.
 */
export function buildSimulationSubscription(
  topics: readonly SimulationStreamTopic[] = SIMULATION_STREAM_TOPICS,
  live = false,
): SimulationSubscriptionPayload {
  const payload: SimulationSubscriptionPayload = {
    type: "subscribe",
    topics: [...topics],
  };
  if (live) {
    payload.live = true;
  }
  return payload;
}

/**
 * Build an empty stream reducer state.
 *
 * @param runId - Simulation run identifier.
 * @returns Initial stream state.
 */
export function buildInitialSimulationStreamState(
  runId: string,
): SimulationStreamState {
  return {
    runId,
    lastEvent: null,
    eventCount: 0,
    countsByTopic: {},
  };
}

/**
 * Reduce a realtime event into stream state.
 *
 * @param state - Current stream state.
 * @param event - Incoming stream event.
 * @returns Updated stream state.
 */
export function reduceSimulationStreamState(
  state: SimulationStreamState,
  event: SimulationStreamEvent,
): SimulationStreamState {
  return {
    runId: state.runId,
    lastEvent: event,
    eventCount: state.eventCount + 1,
    countsByTopic: {
      ...state.countsByTopic,
      [event.topic]: (state.countsByTopic[event.topic] ?? 0) + 1,
    },
  };
}
