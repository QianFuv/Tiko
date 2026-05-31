"""Tests for point-in-time observation building."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from tiko.domain.account import Position, SimAccount
from tiko.domain.market import Candle, FeatureSnapshot, MarketEvent, OrderBookSnapshot
from tiko.domain.memory import MemoryEntry
from tiko.domain.risk import RiskLimits
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


def create_orderbook(symbol: str, hour: int, mid_price: Decimal) -> OrderBookSnapshot:
    """Create an order book snapshot for observation tests.

    Args:
        symbol: Snapshot symbol.
        hour: Snapshot availability hour.
        mid_price: Snapshot mid price.

    Returns:
        Order book snapshot domain model.
    """

    return OrderBookSnapshot(
        symbol=symbol,
        as_of=datetime(2026, 1, 1, hour, tzinfo=UTC),
        bids=[(mid_price - Decimal("1"), Decimal("2"))],
        asks=[(mid_price + Decimal("1"), Decimal("2"))],
        mid_price=mid_price,
        spread_bps=Decimal("2"),
        depth_1pct_usd=Decimal("1000"),
        source=f"orderbook-{hour}",
    )


def create_feature_snapshot(
    run_id: UUID, symbol: str, hour: int, label: str
) -> FeatureSnapshot:
    """Create a feature snapshot for observation tests.

    Args:
        run_id: Simulation run identifier.
        symbol: Snapshot symbol.
        hour: Snapshot availability hour.
        label: Feature value label.

    Returns:
        Feature snapshot domain model.
    """

    return FeatureSnapshot(
        snapshot_id=uuid4(),
        run_id=run_id,
        symbol=symbol,
        as_of=datetime(2026, 1, 1, hour, tzinfo=UTC),
        features={"momentum": label, "hour": hour},
        source=f"features-{hour}",
    )


def create_position(
    run: SimulationRun,
    symbol: str,
    hour: int,
    side: Literal["long", "short", "flat"] = "long",
) -> Position:
    """Create a simulated position for observation tests.

    Args:
        run: Simulation run fixture.
        symbol: Position symbol.
        hour: Position update hour.
        side: Position side.

    Returns:
        Position domain model.
    """

    return Position(
        position_id=uuid4(),
        account_id=run.account.account_id,
        symbol=symbol,
        side=side,
        quantity=Decimal("1"),
        avg_entry_price=Decimal("100"),
        mark_price=Decimal("105"),
        notional=Decimal("105"),
        leverage=Decimal("1"),
        unrealized_pnl=Decimal("5"),
        realized_pnl=Decimal("0"),
        updated_at_sim_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
    )


def create_risk_limits(run_id: UUID) -> RiskLimits:
    """Create active risk limits for observation tests.

    Args:
        run_id: Simulation run identifier.

    Returns:
        Risk limits domain model.
    """

    return RiskLimits(
        run_id=run_id,
        minimum_confidence=0.55,
        minimum_data_quality_score=0.8,
        max_target_weight=Decimal("0.20"),
        max_order_notional=Decimal("500"),
    )


def create_memory_entry(run_id: UUID, hour: int, summary: str) -> MemoryEntry:
    """Create a memory entry for observation tests.

    Args:
        run_id: Simulation run identifier.
        hour: Memory availability hour.
        summary: Memory summary text.

    Returns:
        Memory entry domain model.
    """

    return MemoryEntry(
        memory_id=uuid4(),
        run_id=run_id,
        decision_id=None,
        memory_type="decision",
        summary=summary,
        content={"summary": summary},
        tags=["test"],
        available_at_sim_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, hour, tzinfo=UTC),
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


def test_observation_includes_available_context_without_lookahead() -> None:
    """Verify observations select available context and exclude future inputs."""

    run = create_run()
    as_of = datetime(2026, 1, 1, 2, tzinfo=UTC)
    risk_limits = create_risk_limits(run.run_id)
    prior_position = create_position(run, "BTCUSDT", hour=1)
    future_position = create_position(run, "ETHUSDT", hour=3)
    available_memory = create_memory_entry(run.run_id, 1, "Available memory.")
    future_memory = create_memory_entry(run.run_id, 3, "Future memory.")

    observation = ObservationBuilder().build(
        run=run,
        symbol="BTCUSDT",
        as_of=as_of,
        candles=[create_candle("BTCUSDT", hour=2, as_of_hour=2)],
        events=[],
        orderbooks=[
            create_orderbook("BTCUSDT", 1, Decimal("100")),
            create_orderbook("BTCUSDT", 2, Decimal("105")),
            create_orderbook("BTCUSDT", 3, Decimal("110")),
            create_orderbook("ETHUSDT", 2, Decimal("200")),
        ],
        feature_snapshots=[
            create_feature_snapshot(run.run_id, "BTCUSDT", 1, "stale"),
            create_feature_snapshot(run.run_id, "BTCUSDT", 2, "current"),
            create_feature_snapshot(run.run_id, "BTCUSDT", 3, "future"),
            create_feature_snapshot(uuid4(), "BTCUSDT", 2, "wrong-run"),
        ],
        positions=[prior_position, future_position],
        risk_limits=risk_limits,
        memory_entries=[
            available_memory,
            future_memory,
            create_memory_entry(uuid4(), 1, "Wrong run memory."),
        ],
    )

    assert observation.orderbook is not None
    assert observation.orderbook.mid_price == Decimal("105")
    assert observation.features == {"momentum": "current", "hour": 2}
    assert observation.positions == [prior_position]
    assert observation.risk_limits == risk_limits
    assert observation.memory == [available_memory]
