"""In-memory event bus for deterministic simulation tests."""

from tiko.domain.market import MarketEvent


class EventBus:
    """Collect simulation events in insertion order."""

    def __init__(self) -> None:
        """Initialize an empty event stream."""

        self._events: list[MarketEvent] = []

    def publish(self, event: MarketEvent) -> None:
        """Append an event to the in-memory stream.

        Args:
            event: Market event to record.
        """

        self._events.append(event)

    def list_events(self) -> list[MarketEvent]:
        """Return all recorded events.

        Returns:
            Market events in publish order.
        """

        return list(self._events)
