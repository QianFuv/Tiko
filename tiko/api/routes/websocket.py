"""WebSocket routes for simulation realtime replay streams."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from tiko.api.dependencies import (
    get_realtime_subscriber_service,
    get_simulation_service,
)
from tiko.services import RealtimeFanoutSubscriberService, SimulationService

router = APIRouter(tags=["websocket"])
FANOUT_READ_TIMEOUT_SECONDS = 0.2
LIVE_CONTROL_TIMEOUT_SECONDS = 0.01

SimulationStreamTopic = Literal[
    "market.candle",
    "market.event",
    "agent.run",
    "decision.created",
    "risk.reviewed",
    "order.updated",
    "fill.created",
    "portfolio.updated",
    "alert.created",
    "simulation.status",
    "simulation.heartbeat",
]
SUPPORTED_TOPICS: tuple[SimulationStreamTopic, ...] = (
    "market.candle",
    "market.event",
    "agent.run",
    "decision.created",
    "risk.reviewed",
    "order.updated",
    "fill.created",
    "portfolio.updated",
    "alert.created",
    "simulation.status",
    "simulation.heartbeat",
)
STREAM_PAYLOAD_ID_KEYS = (
    "event_id",
    "agent_run_id",
    "decision_id",
    "review_id",
    "order_id",
    "fill_id",
    "snapshot_id",
    "alert_id",
    "run_id",
)


@dataclass(frozen=True)
class SimulationStreamSubscription:
    """Represent a WebSocket realtime subscription request."""

    topics: tuple[SimulationStreamTopic, ...]
    live: bool


@router.websocket("/ws/simulations/{run_id}")
async def simulation_snapshot_websocket(websocket: WebSocket, run_id: UUID) -> None:
    """Send a recovery snapshot and subscribed replay events for a simulation run.

    Args:
        websocket: WebSocket connection.
        run_id: Simulation run identifier.
    """

    await websocket.accept()
    service = get_simulation_service()
    try:
        run = service.get_run(run_id)
    except KeyError:
        await websocket.send_json(
            {"type": "error", "detail": "Simulation run not found."}
        )
        await websocket.close()
        return
    subscription = await _receive_subscription(websocket)
    topics = subscription.topics
    await websocket.send_json(
        {
            "type": "snapshot",
            "run_id": str(run_id),
            "topics": list(topics),
            "run": jsonable_encoder(run),
            "events": jsonable_encoder(service.list_events(run_id)),
        }
    )
    for event in _build_replay_events(service, run_id, topics):
        await websocket.send_json({"type": "event", **jsonable_encoder(event)})
    await websocket.send_json(
        {
            "type": "replay_complete",
            "run_id": str(run_id),
            "topics": list(topics),
        }
    )
    if not subscription.live or not topics:
        await _close_websocket(websocket)
        return
    subscriber_service = get_realtime_subscriber_service()
    if subscriber_service is None:
        await _close_websocket(websocket)
        return
    await _stream_live_fanout_events(
        websocket=websocket,
        run_id=run_id,
        topics=topics,
        subscriber_service=subscriber_service,
    )


async def _receive_subscription(
    websocket: WebSocket,
) -> SimulationStreamSubscription:
    """Receive an optional subscription payload from a WebSocket client.

    Args:
        websocket: Accepted WebSocket connection.

    Returns:
        Subscription settings, defaulting to replay-only all-topic recovery.
    """

    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=0.05)
    except TimeoutError:
        return SimulationStreamSubscription(topics=SUPPORTED_TOPICS, live=False)
    if not isinstance(payload, dict) or payload.get("type") != "subscribe":
        return SimulationStreamSubscription(topics=SUPPORTED_TOPICS, live=False)
    requested_topics = payload.get("topics")
    if not isinstance(requested_topics, list):
        return SimulationStreamSubscription(
            topics=SUPPORTED_TOPICS,
            live=payload.get("live") is True,
        )
    topics: list[SimulationStreamTopic] = []
    for topic in requested_topics:
        if isinstance(topic, str) and topic in SUPPORTED_TOPICS:
            topics.append(topic)
    return SimulationStreamSubscription(
        topics=tuple(topics),
        live=payload.get("live") is True,
    )


async def _stream_live_fanout_events(
    websocket: WebSocket,
    run_id: UUID,
    topics: tuple[SimulationStreamTopic, ...],
    subscriber_service: RealtimeFanoutSubscriberService,
) -> None:
    """Stream live Redis fanout envelopes to a WebSocket client.

    Args:
        websocket: Accepted WebSocket connection.
        run_id: Simulation run identifier.
        topics: Subscribed realtime topics.
        subscriber_service: Realtime fanout subscriber service.
    """

    subscription = subscriber_service.subscribe(run_id, topics)
    if subscription is None:
        await _close_websocket(websocket)
        return
    try:
        while True:
            if await _receive_live_close(websocket):
                break
            event = await asyncio.to_thread(
                subscription.next_event,
                FANOUT_READ_TIMEOUT_SECONDS,
            )
            if event is None:
                continue
            topic = event.get("topic")
            if isinstance(topic, str) and topic in topics:
                await websocket.send_json({"type": "event", **jsonable_encoder(event)})
    except WebSocketDisconnect:
        pass
    finally:
        subscription.close()
        await _close_websocket(websocket)


async def _receive_live_close(websocket: WebSocket) -> bool:
    """Return whether the live WebSocket client requested closure.

    Args:
        websocket: Accepted WebSocket connection.

    Returns:
        `True` when the client sent a close control payload or disconnected.
    """

    try:
        payload = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=LIVE_CONTROL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return False
    except WebSocketDisconnect:
        return True
    return isinstance(payload, dict) and payload.get("type") == "close"


async def _close_websocket(websocket: WebSocket) -> None:
    """Close a WebSocket connection when still closeable.

    Args:
        websocket: WebSocket connection.
    """

    try:
        await websocket.close()
    except RuntimeError:
        return


def _build_replay_events(
    service: SimulationService,
    run_id: UUID,
    topics: tuple[SimulationStreamTopic, ...],
) -> list[dict[str, object]]:
    """Build deterministic replay event envelopes for subscribed topics.

    Args:
        service: Simulation service.
        run_id: Simulation run identifier.
        topics: Subscribed topics.

    Returns:
        Realtime event envelopes ordered by simulated time and topic.
    """

    if not topics:
        return []
    replay_events: list[dict[str, object]] = []
    stored_events = service.list_realtime_events(run_id)
    for stored_event in stored_events:
        topic = stored_event.get("topic")
        if isinstance(topic, str) and topic in topics:
            replay_events.append(stored_event)
    if "simulation.status" in topics:
        run = service.get_run(run_id)
        replay_events.append(
            _build_stream_event(
                topic="simulation.status",
                run_id=run_id,
                simulated_time=run.current_sim_time,
                payload={
                    "run_id": str(run.run_id),
                    "status": run.status,
                    "current_sim_time": run.current_sim_time.isoformat(),
                    "speed_multiplier": str(run.speed_multiplier),
                },
            )
        )
    if "simulation.heartbeat" in topics:
        run = service.get_run(run_id)
        replay_events.append(
            _build_stream_event(
                topic="simulation.heartbeat",
                run_id=run_id,
                simulated_time=run.current_sim_time,
                payload={
                    "run_id": str(run.run_id),
                    "wall_time": datetime.now(UTC).isoformat(),
                    "simulated_time": run.current_sim_time.isoformat(),
                    "status": run.status,
                    "clock_lag_ms": 0,
                    "event_queue_depth": 0,
                    "worker_status": "healthy",
                },
            )
        )
    if "market.candle" in topics:
        for event in service.list_events(run_id):
            if event.type == "candle_closed":
                replay_events.append(
                    _build_stream_event(
                        topic="market.candle",
                        run_id=run_id,
                        simulated_time=event.simulated_time,
                        payload=event.model_dump(mode="json"),
                    )
                )
    if "agent.run" in topics:
        for agent_run in service.list_agent_runs():
            if agent_run.run_id == run_id:
                replay_events.append(
                    _build_stream_event(
                        topic="agent.run",
                        run_id=run_id,
                        simulated_time=agent_run.completed_at_sim_time,
                        payload=agent_run.model_dump(mode="json"),
                    )
                )
    if "decision.created" in topics:
        for decision in service.list_decisions():
            if decision.run_id == run_id:
                replay_events.append(
                    _build_stream_event(
                        topic="decision.created",
                        run_id=run_id,
                        simulated_time=decision.created_at_sim_time,
                        payload=decision.model_dump(mode="json"),
                    )
                )
    if "risk.reviewed" in topics:
        for review in service.list_risk_reviews(run_id):
            replay_events.append(
                _build_stream_event(
                    topic="risk.reviewed",
                    run_id=run_id,
                    simulated_time=review.created_at_sim_time,
                    payload=review.model_dump(mode="json"),
                )
            )
    if "order.updated" in topics:
        for order in service.list_orders():
            if order.run_id == run_id:
                replay_events.append(
                    _build_stream_event(
                        topic="order.updated",
                        run_id=run_id,
                        simulated_time=order.updated_at_sim_time,
                        payload=order.model_dump(mode="json"),
                    )
                )
    if "fill.created" in topics:
        for fill in service.list_fills():
            if fill.run_id == run_id:
                replay_events.append(
                    _build_stream_event(
                        topic="fill.created",
                        run_id=run_id,
                        simulated_time=fill.filled_at_sim_time,
                        payload=fill.model_dump(mode="json"),
                    )
                )
    if "portfolio.updated" in topics:
        for snapshot in service.list_portfolio_snapshots(run_id):
            replay_events.append(
                _build_stream_event(
                    topic="portfolio.updated",
                    run_id=run_id,
                    simulated_time=snapshot.simulated_time,
                    payload=snapshot.model_dump(mode="json"),
                )
            )
    if "alert.created" in topics:
        for alert in service.list_alerts(run_id):
            replay_events.append(
                _build_stream_event(
                    topic="alert.created",
                    run_id=run_id,
                    simulated_time=alert.created_at_sim_time,
                    payload=alert.model_dump(mode="json"),
                )
            )
    return _sort_replay_events(replay_events)


def _sort_replay_events(
    replay_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Sort replay events while preserving the first copy of each event ID.

    Args:
        replay_events: Realtime event envelopes.

    Returns:
        Unique replay events ordered by simulated time, topic, and ID.
    """

    unique_events: list[dict[str, object]] = []
    seen_event_ids: set[str] = set()
    for event in replay_events:
        event_id = str(event.get("event_id"))
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        unique_events.append(event)
    return sorted(
        unique_events,
        key=lambda event: (
            str(event["simulated_time"]),
            str(event["topic"]),
            str(event["event_id"]),
        ),
    )


def _build_stream_event(
    topic: SimulationStreamTopic,
    run_id: UUID,
    simulated_time: datetime,
    payload: dict[str, object],
) -> dict[str, object]:
    """Build a realtime event envelope.

    Args:
        topic: Realtime topic.
        run_id: Simulation run identifier.
        simulated_time: Simulated event time.
        payload: JSON-serializable event payload.

    Returns:
        Realtime event envelope.
    """

    return {
        "event_id": str(
            uuid5(
                NAMESPACE_URL,
                (
                    f"stream-event:{run_id}:{topic}:"
                    f"{simulated_time.isoformat()}:{_payload_identity(payload)}"
                ),
            )
        ),
        "topic": topic,
        "run_id": str(run_id),
        "simulated_time": simulated_time.isoformat(),
        "payload": payload,
    }


def _payload_identity(payload: dict[str, object]) -> str:
    """Extract stable source identity from a realtime payload.

    Args:
        payload: Realtime event payload.

    Returns:
        Stable identity string for replay event ID generation.
    """

    for key in STREAM_PAYLOAD_ID_KEYS:
        value = payload.get(key)
        if value is not None:
            return f"{key}:{value}"
    return "payload:none"
