"""Tests for point-in-time observation building."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tiko.domain.account import SimAccount
from tiko.domain.market import Candle, MarketEvent
from tiko.domain.simulation import SimulationRun
from tiko.observation import ObservationBuilder


def create_account() -> SimAccount:
    """Create a simulated account for observation tests.

    Returns:
        Simulated account domain model.
    """

    return SimAccount(
        account_id=uuid4(),
        name="observation-account",
        initial_equity=Decimal("1000"),
        cash_balance=Decimal("1000"),
        total_equity=Decimal("1000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
    )


def create_run() -> SimulationRun:
    """Create a simulation run for observation tests.

    Returns:
        Simulation run domain model.
    """

    return SimulationRun(
        run_id=uuid4(),
        name="observation-run",
        status="running",
        mode="historical_replay",
        account=create_account(),
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        current_sim_time=datetime(2026, 1, 1, 3, tzinfo=UTC),
        config={"data_source": "replay"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_candle(symbol: str, hour: int, as_of_hour: int) -> Candle:
    """Create a candle for observation tests.

    Args:
        symbol: Candle symbol.
        hour: Candle close hour.
        as_of_hour: Candle availability hour.

    Returns:
        Candle domain model.
    """

    return Candle(
        symbol=symbol,
        timeframe="1h",
        open_time=datetime(2026, 1, 1, hour - 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal(hour),
        volume=Decimal("1"),
        quote_volume=None,
        source="test",
        as_of=datetime(2026, 1, 1, as_of_hour, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, as_of_hour, tzinfo=UTC),
    )


def create_event(symbol: str | None, hour: int) -> MarketEvent:
    """Create a market event for observation tests.

    Args:
        symbol: Event symbol or `None` for global event.
        hour: Event simulated hour.

    Returns:
        Market event domain model.
    """

    return MarketEvent(
        event_id=uuid4(),
        type="news_event",
        symbol=symbol,
        simulated_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
        payload={"headline": f"event-{hour}"},
        source="test",
        confidence=1.0,
    )


def test_observation_excludes_future_and_wrong_symbol_data() -> None:
    """Verify observations do not include unavailable candles or events."""

    as_of = datetime(2026, 1, 1, 2, tzinfo=UTC)
    observation = ObservationBuilder().build(
        run=create_run(),
        symbol="BTCUSDT",
        as_of=as_of,
        candles=[
            create_candle("BTCUSDT", hour=1, as_of_hour=1),
            create_candle("BTCUSDT", hour=2, as_of_hour=3),
            create_candle("ETHUSDT", hour=1, as_of_hour=1),
        ],
        events=[
            create_event("BTCUSDT", hour=1),
            create_event("BTCUSDT", hour=3),
            create_event("ETHUSDT", hour=1),
            create_event(None, hour=2),
        ],
    )

    assert [candle.close for candle in observation.candles] == [Decimal("1")]
    assert [event.payload["headline"] for event in observation.events] == [
        "event-1",
        "event-2",
    ]


def test_observation_applies_latest_candle_lookback() -> None:
    """Verify observation candle history is bounded to the latest records."""

    observation = ObservationBuilder(candle_lookback=2).build(
        run=create_run(),
        symbol="BTCUSDT",
        as_of=datetime(2026, 1, 1, 4, tzinfo=UTC),
        candles=[
            create_candle("BTCUSDT", hour=1, as_of_hour=1),
            create_candle("BTCUSDT", hour=2, as_of_hour=2),
            create_candle("BTCUSDT", hour=3, as_of_hour=3),
        ],
    )

    assert [candle.close for candle in observation.candles] == [
        Decimal("2"),
        Decimal("3"),
    ]


def test_observation_uses_stable_observation_id() -> None:
    """Verify caller-supplied observation IDs are preserved."""

    observation_id = UUID("00000000-0000-0000-0000-000000000123")

    observation = ObservationBuilder().build(
        run=create_run(),
        symbol="BTCUSDT",
        as_of=datetime(2026, 1, 1, 1, tzinfo=UTC),
        candles=[create_candle("BTCUSDT", hour=1, as_of_hour=1)],
        observation_id=observation_id,
    )

    assert observation.observation_id == observation_id
