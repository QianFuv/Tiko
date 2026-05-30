"""Tests for deterministic candle market replay."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tiko.domain.market import Candle
from tiko.simulation.replay import MarketReplay, MarketReplayExhausted


def create_candle(symbol: str, close_hour: int, as_of_hour: int) -> Candle:
    """Create a replay test candle.

    Args:
        symbol: Candle symbol.
        close_hour: Close hour on 2026-01-01 UTC.
        as_of_hour: Availability hour on 2026-01-01 UTC.

    Returns:
        Candle domain model.
    """

    close_time = datetime(2026, 1, 1, close_hour, tzinfo=UTC)
    as_of = datetime(2026, 1, 1, as_of_hour, tzinfo=UTC)
    return Candle(
        symbol=symbol,
        timeframe="1h",
        open_time=datetime(2026, 1, 1, close_hour - 1, tzinfo=UTC),
        close_time=close_time,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1"),
        quote_volume=None,
        source="test",
        as_of=as_of,
        created_at=as_of,
    )


def test_market_replay_orders_by_availability_close_time_and_symbol() -> None:
    """Verify replay order is deterministic and point-in-time safe."""

    replay = MarketReplay(
        candles=[
            create_candle("ETHUSDT", close_hour=1, as_of_hour=2),
            create_candle("BTCUSDT", close_hour=1, as_of_hour=1),
            create_candle("ADAUSDT", close_hour=1, as_of_hour=1),
        ],
        symbols=["BTCUSDT", "ETHUSDT", "ADAUSDT"],
    )

    assert replay.next_candle().symbol == "ADAUSDT"
    assert replay.next_candle().symbol == "BTCUSDT"
    assert replay.next_candle().symbol == "ETHUSDT"
    assert not replay.has_next()


def test_market_replay_filters_to_requested_symbols() -> None:
    """Verify replay ignores candles outside the run symbol universe."""

    replay = MarketReplay(
        candles=[
            create_candle("BTCUSDT", close_hour=1, as_of_hour=1),
            create_candle("ETHUSDT", close_hour=1, as_of_hour=1),
        ],
        symbols=["ETHUSDT"],
    )

    assert replay.remaining() == 1
    assert replay.next_candle().symbol == "ETHUSDT"


def test_market_replay_raises_when_exhausted() -> None:
    """Verify exhausted replay fails loudly."""

    replay = MarketReplay(
        candles=[create_candle("BTCUSDT", close_hour=1, as_of_hour=1)],
        symbols=["BTCUSDT"],
    )
    replay.next_candle()

    with pytest.raises(MarketReplayExhausted):
        replay.next_candle()


def test_market_replay_rejects_empty_matching_dataset() -> None:
    """Verify replay cannot start without matching candles."""

    with pytest.raises(ValueError, match="matching candle"):
        MarketReplay(
            candles=[create_candle("BTCUSDT", close_hour=1, as_of_hour=1)],
            symbols=["ETHUSDT"],
        )
