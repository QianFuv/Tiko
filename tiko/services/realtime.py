"""Realtime fanout services for Redis-compatible Pub/Sub."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import redis

from tiko.simulation.state import SimulationStepResult

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


class RedisPublishClient(Protocol):
    """Define the synchronous Redis publish subset used by fanout."""

    def ping(self) -> object:
        """Verify client connectivity.

        Returns:
            Redis ping response.
        """

    def publish(self, channel: str, message: str) -> object:
        """Publish one message to a Redis channel.

        Args:
            channel: Redis Pub/Sub channel.
            message: Serialized message payload.

        Returns:
            Redis subscriber count response.
        """


class RedisPubSubClient(Protocol):
    """Define the synchronous Redis Pub/Sub subset used by subscribers."""

    def subscribe(self, *channels: str) -> object:
        """Subscribe to Redis Pub/Sub channels.

        Args:
            channels: Redis Pub/Sub channels.

        Returns:
            Redis subscribe response.
        """

    def get_message(
        self,
        ignore_subscribe_messages: bool = False,
        timeout: float = 0.0,
    ) -> object | None:
        """Read one Redis Pub/Sub message when available.

        Args:
            ignore_subscribe_messages: Whether subscription confirmations are skipped.
            timeout: Maximum blocking read duration in seconds.

        Returns:
            Redis message object or `None`.
        """

    def close(self) -> object:
        """Close the Redis Pub/Sub connection.

        Returns:
            Redis close response.
        """


class RedisSubscribeClient(Protocol):
    """Define the Redis subset used to create Pub/Sub subscribers."""

    def pubsub(self) -> RedisPubSubClient:
        """Create a Redis Pub/Sub client.

        Returns:
            Redis Pub/Sub client.
        """


@dataclass(frozen=True)
class RealtimeFanoutReceipt:
    """Summarize one realtime fanout publish attempt."""

    channel: str
    subscriber_count: int
    published: bool


class RealtimeFanoutService:
    """Publish realtime envelopes to Redis-compatible Pub/Sub channels."""

    def __init__(
        self,
        redis_url: str | None = None,
        client: RedisPublishClient | None = None,
        channel_prefix: str = "tiko:realtime",
    ) -> None:
        """Initialize the fanout service.

        Args:
            redis_url: Optional Redis connection URL.
            client: Optional already-configured Redis-compatible client.
            channel_prefix: Prefix used for generated Pub/Sub channels.

        Raises:
            ValueError: If the channel prefix is empty.
        """

        normalized_prefix = channel_prefix.strip(":")
        if not normalized_prefix:
            raise ValueError("Realtime fanout channel prefix must not be empty.")
        self._channel_prefix = normalized_prefix
        self._client = client
        if self._client is None and redis_url:
            self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def is_configured(self) -> bool:
        """Return whether a publish client is configured.

        Returns:
            `True` when Redis publishing is configured.
        """

        return self._client is not None

    def ping(self) -> bool:
        """Verify Redis connectivity when configured.

        Returns:
            `True` when the configured client responds to ping.
        """

        if self._client is None:
            return False
        return bool(self._client.ping())

    def publish(self, envelope: dict[str, object]) -> RealtimeFanoutReceipt:
        """Publish one realtime event envelope.

        Args:
            envelope: Realtime event envelope containing `run_id` and `topic`.

        Returns:
            Fanout publish receipt.

        Raises:
            ValueError: If the envelope does not include required fields.
        """

        channel = self._build_channel(envelope)
        if self._client is None:
            return RealtimeFanoutReceipt(
                channel=channel,
                subscriber_count=0,
                published=False,
            )
        message = json.dumps(
            envelope,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
        subscriber_count = self._parse_subscriber_count(
            self._client.publish(channel, message)
        )
        return RealtimeFanoutReceipt(
            channel=channel,
            subscriber_count=subscriber_count,
            published=True,
        )

    def publish_many(
        self, envelopes: list[dict[str, object]]
    ) -> tuple[RealtimeFanoutReceipt, ...]:
        """Publish multiple realtime event envelopes.

        Args:
            envelopes: Realtime event envelopes.

        Returns:
            Fanout publish receipts in input order.
        """

        return tuple(self.publish(envelope) for envelope in envelopes)

    def _build_channel(self, envelope: dict[str, object]) -> str:
        """Build the Redis channel for one realtime envelope.

        Args:
            envelope: Realtime event envelope.

        Returns:
            Redis Pub/Sub channel.

        Raises:
            ValueError: If the envelope does not include required fields.
        """

        run_id = self._read_required_string(envelope, "run_id")
        topic = self._read_required_string(envelope, "topic")
        return f"{self._channel_prefix}:{run_id}:{topic}"

    def _read_required_string(self, envelope: dict[str, object], key: str) -> str:
        """Read a required non-empty envelope string field.

        Args:
            envelope: Realtime event envelope.
            key: Required envelope key.

        Returns:
            Non-empty string value.

        Raises:
            ValueError: If the value is missing or empty.
        """

        value = envelope.get(key)
        if value is None:
            raise ValueError(f"Realtime envelope field {key} is required.")
        text = str(value)
        if not text:
            raise ValueError(f"Realtime envelope field {key} must not be empty.")
        return text

    def _parse_subscriber_count(self, value: object) -> int:
        """Parse a Redis publish subscriber count response.

        Args:
            value: Redis publish response.

        Returns:
            Subscriber count.

        Raises:
            ValueError: If the response is not integer-like.
        """

        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        raise ValueError("Redis publish response must be an integer subscriber count.")


class RealtimeFanoutSubscription:
    """Read decoded realtime envelopes from a Redis Pub/Sub subscription."""

    def __init__(
        self,
        pubsub: RedisPubSubClient,
        channels: Sequence[str],
    ) -> None:
        """Initialize a live fanout subscription.

        Args:
            pubsub: Redis Pub/Sub client.
            channels: Subscribed channels.
        """

        self._pubsub = pubsub
        self.channels = tuple(channels)

    def next_event(self, timeout_seconds: float = 1.0) -> dict[str, object] | None:
        """Read and decode the next realtime envelope when available.

        Args:
            timeout_seconds: Maximum blocking read duration in seconds.

        Returns:
            Realtime event envelope or `None` when no event is available.

        Raises:
            json.JSONDecodeError: If Redis returns invalid JSON.
        """

        message = self._pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=timeout_seconds,
        )
        if not isinstance(message, dict) or message.get("type") != "message":
            return None
        data = message.get("data")
        if isinstance(data, bytes):
            text = data.decode("utf-8")
        elif isinstance(data, str):
            text = data
        else:
            return None
        decoded = json.loads(text)
        if not isinstance(decoded, dict):
            return None
        return decoded

    def close(self) -> None:
        """Close the underlying Redis Pub/Sub subscription."""

        self._pubsub.close()


class RealtimeFanoutSubscriberService:
    """Subscribe to Redis-compatible realtime fanout channels."""

    def __init__(
        self,
        redis_url: str | None = None,
        client: RedisSubscribeClient | None = None,
        channel_prefix: str = "tiko:realtime",
    ) -> None:
        """Initialize the subscriber service.

        Args:
            redis_url: Optional Redis connection URL.
            client: Optional already-configured Redis-compatible client.
            channel_prefix: Prefix used for generated Pub/Sub channels.

        Raises:
            ValueError: If the channel prefix is empty.
        """

        normalized_prefix = channel_prefix.strip(":")
        if not normalized_prefix:
            raise ValueError("Realtime fanout channel prefix must not be empty.")
        self._channel_prefix = normalized_prefix
        self._client = client
        if self._client is None and redis_url:
            self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def is_configured(self) -> bool:
        """Return whether a subscription client is configured.

        Returns:
            `True` when Redis subscribing is configured.
        """

        return self._client is not None

    def subscribe(
        self,
        run_id: UUID,
        topics: Sequence[str],
    ) -> RealtimeFanoutSubscription | None:
        """Subscribe to realtime fanout channels for one simulation run.

        Args:
            run_id: Simulation run identifier.
            topics: Realtime topics.

        Returns:
            Fanout subscription or `None` when no client or topics are configured.
        """

        if self._client is None or not topics:
            return None
        channels = tuple(self.build_channel(run_id, topic) for topic in topics)
        pubsub = self._client.pubsub()
        pubsub.subscribe(*channels)
        return RealtimeFanoutSubscription(pubsub, channels)

    def build_channel(self, run_id: UUID, topic: str) -> str:
        """Build a Redis Pub/Sub channel for a run topic.

        Args:
            run_id: Simulation run identifier.
            topic: Realtime topic.

        Returns:
            Redis Pub/Sub channel.
        """

        return f"{self._channel_prefix}:{run_id}:{topic}"


def build_step_result_envelopes(
    result: SimulationStepResult,
) -> list[dict[str, object]]:
    """Build realtime envelopes for one completed simulation step.

    Args:
        result: Simulation step result.

    Returns:
        Realtime event envelopes in publish order.
    """

    run_id = result.run.run_id
    simulated_time = result.run.current_sim_time
    envelopes = [
        build_stream_event(
            topic="market.candle",
            run_id=run_id,
            simulated_time=result.event.simulated_time,
            payload=result.event.model_dump(mode="json"),
        ),
        build_stream_event(
            topic="agent.run",
            run_id=run_id,
            simulated_time=result.agent_run.completed_at_sim_time,
            payload=result.agent_run.model_dump(mode="json"),
        ),
        build_stream_event(
            topic="decision.created",
            run_id=run_id,
            simulated_time=result.decision.created_at_sim_time,
            payload=result.decision.model_dump(mode="json"),
        ),
        build_stream_event(
            topic="risk.reviewed",
            run_id=run_id,
            simulated_time=result.risk_review.created_at_sim_time,
            payload=result.risk_review.model_dump(mode="json"),
        ),
    ]
    if result.order is not None:
        envelopes.append(
            build_stream_event(
                topic="order.updated",
                run_id=run_id,
                simulated_time=result.order.updated_at_sim_time,
                payload=result.order.model_dump(mode="json"),
            )
        )
    if result.fill is not None:
        envelopes.append(
            build_stream_event(
                topic="fill.created",
                run_id=run_id,
                simulated_time=result.fill.filled_at_sim_time,
                payload=result.fill.model_dump(mode="json"),
            )
        )
    envelopes.extend(
        [
            build_stream_event(
                topic="portfolio.updated",
                run_id=run_id,
                simulated_time=result.portfolio_snapshot.simulated_time,
                payload=result.portfolio_snapshot.model_dump(mode="json"),
            ),
            build_stream_event(
                topic="simulation.status",
                run_id=run_id,
                simulated_time=simulated_time,
                payload={
                    "run_id": str(run_id),
                    "status": result.run.status,
                    "current_sim_time": simulated_time.isoformat(),
                    "speed_multiplier": str(result.run.speed_multiplier),
                },
            ),
            build_stream_event(
                topic="simulation.heartbeat",
                run_id=run_id,
                simulated_time=simulated_time,
                payload={
                    "run_id": str(run_id),
                    "wall_time": datetime.now(UTC).isoformat(),
                    "simulated_time": simulated_time.isoformat(),
                    "status": result.run.status,
                    "clock_lag_ms": 0,
                    "event_queue_depth": 0,
                    "worker_status": "healthy",
                },
            ),
        ]
    )
    return envelopes


def build_stream_event(
    topic: str,
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
        Stable identity string for event ID generation.
    """

    for key in STREAM_PAYLOAD_ID_KEYS:
        value = payload.get(key)
        if value is not None:
            return f"{key}:{value}"
    return "payload:none"
