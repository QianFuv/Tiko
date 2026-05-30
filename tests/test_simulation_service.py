"""Tests for deterministic in-memory simulation service behavior."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tiko.core.config import Settings
from tiko.services import SimulationService


def test_simulation_step_creates_internal_order_and_fill() -> None:
    """Verify one simulation step creates simulated execution artifacts."""

    service = SimulationService(Settings())
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    run = service.create_run(
        name="demo",
        symbols=["BTCUSDT"],
        start_sim_time=start_time,
    )

    result = service.step_run(run.run_id)

    assert result.run.current_sim_time == start_time + timedelta(hours=1)
    assert result.candle.close == Decimal("50035")
    assert result.risk_review.status == "approved"
    assert result.order is not None
    assert result.fill is not None
    assert result.run.account.realized_pnl < Decimal("0")
    assert len(service.list_orders()) == 1
    assert len(service.list_fills()) == 1


def test_simulation_step_is_deterministic_for_observable_market_values() -> None:
    """Verify repeated runs with the same inputs produce the same market result."""

    first_service = SimulationService(Settings())
    second_service = SimulationService(Settings())
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    first_run = first_service.create_run("first", ["BTCUSDT"], start_time)
    second_run = second_service.create_run("second", ["BTCUSDT"], start_time)

    first_result = first_service.step_run(first_run.run_id)
    second_result = second_service.step_run(second_run.run_id)

    assert first_result.candle.model_dump(exclude={"created_at"}) == (
        second_result.candle.model_dump(exclude={"created_at"})
    )
    assert first_result.risk_review.status == second_result.risk_review.status
    assert first_result.fill is not None
    assert second_result.fill is not None
    assert first_result.fill.price == second_result.fill.price


def test_low_confidence_intent_is_rejected_without_order() -> None:
    """Verify risk rejection prevents simulated order creation."""

    service = SimulationService(Settings(minimum_trade_confidence=0.55))
    run = service.create_run(
        name="risk",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = service.step_run(run.run_id, confidence=0.2)

    assert result.risk_review.status == "rejected"
    assert result.order is None
    assert result.fill is None
    assert service.list_orders() == []
    assert service.list_fills() == []
