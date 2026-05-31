"use client";

import { useEffect, useMemo, useState, type ReactElement } from "react";

import { formatDateTime } from "@/lib/format";
import {
  buildInitialSimulationStreamState,
  buildSimulationSubscription,
  buildSimulationWebSocketUrl,
  reduceSimulationStreamState,
  SIMULATION_STREAM_TOPICS,
  type SimulationStreamEvent,
  type SimulationStreamState,
  type SimulationStreamTopic,
} from "@/lib/websocket";

type StreamConnectionStatus = "connecting" | "open" | "closed" | "unavailable";

type IncomingStreamEvent = SimulationStreamEvent & {
  type: "event";
};

type SimulationStreamPanelProps = {
  runId: string;
  apiBaseUrl: string;
};

/**
 * Render live WebSocket reducer state for one simulation run.
 *
 * @param props - Stream panel props.
 * @returns Simulation stream panel.
 */
export function SimulationStreamPanel({
  runId,
  apiBaseUrl,
}: SimulationStreamPanelProps): ReactElement {
  const [connectionStatus, setConnectionStatus] =
    useState<StreamConnectionStatus>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [heartbeatPayload, setHeartbeatPayload] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [streamState, setStreamState] = useState<SimulationStreamState>(() =>
    buildInitialSimulationStreamState(runId),
  );
  const topicCounts = useMemo(
    () =>
      SIMULATION_STREAM_TOPICS.map((topic) => ({
        topic,
        count: streamState.countsByTopic[topic] ?? 0,
      })),
    [streamState.countsByTopic],
  );

  useEffect(() => {
    let isActive = true;
    const websocket = new WebSocket(
      buildSimulationWebSocketUrl(apiBaseUrl, runId),
    );

    websocket.addEventListener("open", () => {
      if (!isActive) {
        return;
      }
      setConnectionStatus("open");
      setErrorMessage(null);
      setCompletedAt(null);
      websocket.send(
        JSON.stringify(
          buildSimulationSubscription(SIMULATION_STREAM_TOPICS, true),
        ),
      );
    });

    websocket.addEventListener("message", (event: MessageEvent<unknown>) => {
      if (!isActive || typeof event.data !== "string") {
        return;
      }
      const message = parseStreamMessage(event.data);
      if (isIncomingStreamEvent(message)) {
        setStreamState((currentState) =>
          reduceSimulationStreamState(currentState, message),
        );
        if (message.topic === "simulation.heartbeat") {
          setHeartbeatPayload(message.payload);
        }
        return;
      }
      if (isReplayCompleteMessage(message)) {
        setCompletedAt(new Date().toISOString());
      }
    });

    websocket.addEventListener("error", () => {
      if (!isActive) {
        return;
      }
      setConnectionStatus("unavailable");
      setErrorMessage("Stream unavailable");
    });

    websocket.addEventListener("close", () => {
      if (!isActive) {
        return;
      }
      setConnectionStatus("closed");
    });

    return () => {
      isActive = false;
      websocket.close();
    };
  }, [apiBaseUrl, runId]);

  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Realtime Stream</h2>
        <span
          className={`rounded-md border px-2 py-1 text-xs font-medium ${connectionStatusClass(
            connectionStatus,
          )}`}
        >
          {formatConnectionStatus(connectionStatus)}
        </span>
      </div>

      <div className="mt-3 rounded-lg border border-[#d8dee4] bg-white p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <StreamStat label="Events" value={String(streamState.eventCount)} />
          <StreamStat
            label="Last topic"
            value={streamState.lastEvent?.topic ?? "None"}
          />
          <StreamStat
            label="Replay"
            value={completedAt ? formatDateTime(completedAt) : "Recovering"}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-[#44504b]">
          {topicCounts.map(({ topic, count }) => (
            <div
              key={topic}
              className="flex min-h-8 items-center justify-between rounded-md border border-[#edf0f2] px-2"
            >
              <span className="truncate">{topic}</span>
              <span className="font-semibold text-[#17201b]">{count}</span>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-2 border-t border-[#edf0f2] pt-3 text-sm">
          <RuntimeLine
            label="Heartbeat"
            value={formatPayloadValue(heartbeatPayload?.status)}
          />
          <RuntimeLine
            label="Lag"
            value={`${formatPayloadValue(heartbeatPayload?.clock_lag_ms)} ms`}
          />
          <RuntimeLine
            label="Queue"
            value={formatPayloadValue(heartbeatPayload?.event_queue_depth)}
          />
          <RuntimeLine
            label="Worker"
            value={formatPayloadValue(heartbeatPayload?.worker_status)}
          />
        </div>

        {errorMessage ? (
          <p className="mt-3 rounded-md border border-[#e8b2aa] bg-[#fff5f3] px-3 py-2 text-sm text-[#7a2318]">
            {errorMessage}
          </p>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Render one compact stream statistic.
 *
 * @param props - Statistic props.
 * @returns Stream statistic element.
 */
function StreamStat({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="rounded-md border border-[#edf0f2] bg-[#f8faf9] px-3 py-2">
      <div className="text-xs text-[#6c7671]">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold text-[#17201b]">
        {value}
      </div>
    </div>
  );
}

/**
 * Render one runtime metadata line.
 *
 * @param props - Runtime line props.
 * @returns Runtime metadata row.
 */
function RuntimeLine({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[#6c7671]">{label}</span>
      <span className="font-medium text-[#17201b]">{value}</span>
    </div>
  );
}

/**
 * Parse one stream message payload.
 *
 * @param value - Raw WebSocket message value.
 * @returns Parsed JSON message or `null`.
 */
function parseStreamMessage(value: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return null;
  }
}

/**
 * Check whether a parsed message is a simulation stream event.
 *
 * @param value - Parsed WebSocket message.
 * @returns Whether the value is an event envelope.
 */
function isIncomingStreamEvent(value: unknown): value is IncomingStreamEvent {
  if (!isRecord(value)) {
    return false;
  }
  return (
    value.type === "event" &&
    typeof value.event_id === "string" &&
    isSimulationStreamTopic(value.topic) &&
    typeof value.run_id === "string" &&
    typeof value.simulated_time === "string" &&
    isRecord(value.payload)
  );
}

/**
 * Check whether a parsed message marks replay completion.
 *
 * @param value - Parsed WebSocket message.
 * @returns Whether the value is a replay completion message.
 */
function isReplayCompleteMessage(value: unknown): boolean {
  return isRecord(value) && value.type === "replay_complete";
}

/**
 * Check whether a value is a known stream topic.
 *
 * @param value - Parsed topic value.
 * @returns Whether the value is a simulation stream topic.
 */
function isSimulationStreamTopic(
  value: unknown,
): value is SimulationStreamTopic {
  return (
    typeof value === "string" &&
    SIMULATION_STREAM_TOPICS.includes(value as SimulationStreamTopic)
  );
}

/**
 * Check whether a value is a non-null object record.
 *
 * @param value - Value to inspect.
 * @returns Whether the value is a record.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Format the connection status for display.
 *
 * @param status - Connection status.
 * @returns Human-readable status.
 */
function formatConnectionStatus(status: StreamConnectionStatus): string {
  if (status === "open") {
    return "Open";
  }
  if (status === "closed") {
    return "Closed";
  }
  if (status === "unavailable") {
    return "Unavailable";
  }
  return "Connecting";
}

/**
 * Resolve a status badge class.
 *
 * @param status - Connection status.
 * @returns CSS class list.
 */
function connectionStatusClass(status: StreamConnectionStatus): string {
  if (status === "open") {
    return "border-[#9bc5ae] bg-[#f4fbf6] text-[#173f2a]";
  }
  if (status === "unavailable") {
    return "border-[#e8b2aa] bg-[#fff5f3] text-[#7a2318]";
  }
  return "border-[#d8dee4] bg-[#f8faf9] text-[#44504b]";
}

/**
 * Format an unknown heartbeat payload value.
 *
 * @param value - Payload value.
 * @returns Display value.
 */
function formatPayloadValue(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return "Pending";
}
