"""WebSocket routes for simulation realtime replay streams."""

import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket
from fastapi.encoders import jsonable_encoder

from tiko.api.dependencies import get_simulation_service
from tiko.services import SimulationService

router = APIRouter(tags=["websocket"])

SimulationStreamTopic = Literal[
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
]
SUPPORTED_TOPICS: tuple[SimulationStreamTopic, ...] = (
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
)


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
    topics = await _receive_subscription_topics(websocket)
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
    await websocket.close()


async def _receive_subscription_topics(
    websocket: WebSocket,
) -> tuple[SimulationStreamTopic, ...]:
    """Receive an optional subscription payload from a websocket client.

    Args:
        websocket: Accepted WebSocket connection.

    Returns:
        Subscribed topics, defaulting to all supported topics.
    """

    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=0.05)
    except TimeoutError:
        return SUPPORTED_TOPICS
    if not isinstance(payload, dict) or payload.get("type") != "subscribe":
        return SUPPORTED_TOPICS
    requested_topics = payload.get("topics")
    if not isinstance(requested_topics, list):
        return SUPPORTED_TOPICS
    topics: list[SimulationStreamTopic] = []
    for topic in requested_topics:
        if isinstance(topic, str) and topic in SUPPORTED_TOPICS:
            topics.append(topic)
    return tuple(topics)


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
    return sorted(
        replay_events,
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
        "event_id": str(uuid4()),
        "topic": topic,
        "run_id": str(run_id),
        "simulated_time": simulated_time.isoformat(),
        "payload": payload,
    }
