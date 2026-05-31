"""Realtime fanout services for Redis-compatible Pub/Sub."""

import json
from dataclasses import dataclass
from typing import Protocol

import redis


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
