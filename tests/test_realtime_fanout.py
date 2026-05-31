"""Tests for Redis-compatible realtime fanout services."""

import json
from uuid import uuid4

import pytest

from tiko.core.config import Settings
from tiko.services import RealtimeFanoutService


class FakeRedisPublisher:
    """Fake Redis publisher that records published messages."""

    def __init__(self, subscriber_count: int = 2) -> None:
        """Initialize the fake publisher.

        Args:
            subscriber_count: Subscriber count returned by publish calls.
        """

        self.subscriber_count = subscriber_count
        self.messages: list[tuple[str, str]] = []
        self.did_ping = False

    def ping(self) -> bool:
        """Record and return a successful ping response.

        Returns:
            Successful ping response.
        """

        self.did_ping = True
        return True

    def publish(self, channel: str, message: str) -> int:
        """Record one publish call.

        Args:
            channel: Redis channel.
            message: Serialized message payload.

        Returns:
            Fake subscriber count.
        """

        self.messages.append((channel, message))
        return self.subscriber_count


def create_realtime_envelope() -> dict[str, object]:
    """Create a deterministic realtime envelope fixture.

    Returns:
        Realtime event envelope.
    """

    run_id = uuid4()
    return {
        "event_id": str(uuid4()),
        "topic": "decision.created",
        "run_id": str(run_id),
        "simulated_time": "2026-01-01T01:00:00+00:00",
        "payload": {"run_id": str(run_id), "decision_id": str(uuid4())},
    }


def test_realtime_fanout_publishes_envelopes_to_redis_channels() -> None:
    """Verify realtime envelopes publish as JSON to deterministic channels."""

    client = FakeRedisPublisher(subscriber_count=3)
    service = RealtimeFanoutService(client=client, channel_prefix="tiko:test")
    envelope = create_realtime_envelope()

    receipt = service.publish(envelope)

    assert service.is_configured() is True
    assert service.ping() is True
    assert client.did_ping is True
    assert receipt.published is True
    assert receipt.subscriber_count == 3
    assert receipt.channel == (f"tiko:test:{envelope['run_id']}:{envelope['topic']}")
    assert len(client.messages) == 1
    assert client.messages[0][0] == receipt.channel
    assert json.loads(client.messages[0][1]) == envelope


def test_realtime_fanout_returns_disabled_receipts_without_redis() -> None:
    """Verify local runs without Redis do not fail publishing attempts."""

    service = RealtimeFanoutService(channel_prefix="tiko:test")
    envelope = create_realtime_envelope()

    receipt = service.publish(envelope)

    assert service.is_configured() is False
    assert service.ping() is False
    assert receipt.published is False
    assert receipt.subscriber_count == 0
    assert receipt.channel == (f"tiko:test:{envelope['run_id']}:{envelope['topic']}")


def test_realtime_fanout_validates_required_envelope_fields() -> None:
    """Verify missing channel identity fields are rejected."""

    service = RealtimeFanoutService(channel_prefix="tiko:test")

    with pytest.raises(ValueError, match="run_id"):
        service.publish({"topic": "decision.created"})

    with pytest.raises(ValueError, match="topic"):
        service.publish({"run_id": str(uuid4())})

    with pytest.raises(ValueError, match="prefix"):
        RealtimeFanoutService(channel_prefix=":")


def test_realtime_fanout_publishes_multiple_envelopes_in_order() -> None:
    """Verify multiple realtime envelopes publish in input order."""

    client = FakeRedisPublisher()
    service = RealtimeFanoutService(client=client, channel_prefix="tiko:test")
    envelopes = [create_realtime_envelope(), create_realtime_envelope()]

    receipts = service.publish_many(envelopes)

    assert tuple(receipt.channel for receipt in receipts) == tuple(
        channel for channel, _message in client.messages
    )
    assert [json.loads(message) for _channel, message in client.messages] == envelopes


def test_settings_loads_redis_url_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings load Redis URLs from deployment environment aliases."""

    monkeypatch.setenv("TIKO_REDIS_URL", "redis://redis:6379/0")

    settings = Settings()

    assert settings.redis_url == "redis://redis:6379/0"
