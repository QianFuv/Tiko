"""Tests for deterministic in-memory simulation service behavior."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tiko.core.config import Settings
from tiko.db import (
    SimulationRepository,
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
from tiko.domain.market import Candle
from tiko.services import SimulationService
from tiko.simulation.replay import MarketReplayExhausted


def create_test_repository() -> SimulationRepository:
    """Create an in-memory repository for service integration tests.

    Returns:
        Simulation repository bound to an in-memory SQLite database.
    """

    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    create_all_tables(engine)
    return SimulationRepository(create_session_factory(engine))


def create_replay_candle() -> Candle:
    """Create a replay candle with delayed point-in-time availability.

    Returns:
        Candle for replay-backed service tests.
    """

    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=datetime(2026, 1, 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("2"),
        quote_volume=None,
        source="replay-test",
        as_of=datetime(2026, 1, 1, 2, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
    )


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
    assert result.observation.symbol == "BTCUSDT"
    assert result.agent_run.decision_id == result.decision.decision_id
    assert [message.role for message in result.agent_messages] == [
        "system",
        "observation",
        "assistant",
    ]
    assert result.order is not None
    assert result.fill is not None
    assert result.ledger_entry is not None
    assert len(result.positions) == 1
    assert result.portfolio_snapshot.gross_exposure > Decimal("0")
    assert result.metric_snapshot.metrics["fill_count"] == 1
    assert result.run.account.realized_pnl < Decimal("0")
    assert len(service.list_orders()) == 1
    assert len(service.list_fills()) == 1
    assert service.list_observation_snapshots(run.run_id) == [result.observation]
    assert service.list_agent_runs() == [result.agent_run]
    assert service.list_agent_messages(result.agent_run.agent_run_id) == list(
        result.agent_messages
    )
    assert service.list_positions(run.run_id) == list(result.positions)
    assert service.list_ledger_entries(run.run_id) == [result.ledger_entry]
    assert service.list_portfolio_snapshots(run.run_id) == [result.portfolio_snapshot]
    assert service.list_metric_snapshots(run.run_id) == [result.metric_snapshot]


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
    assert result.observation.symbol == "BTCUSDT"
    assert result.agent_run.decision_id == result.decision.decision_id
    assert len(result.agent_messages) == 3
    assert result.order is None
    assert result.fill is None
    assert result.ledger_entry is None
    assert result.positions == ()
    assert result.metric_snapshot.metrics["fill_count"] == 0
    assert service.list_orders() == []
    assert service.list_fills() == []
    assert service.list_ledger_entries(run.run_id) == []
    assert service.list_portfolio_snapshots(run.run_id) == [result.portfolio_snapshot]


def test_repository_backed_service_persists_created_run_and_step() -> None:
    """Verify optional persistence hooks write service-generated artifacts."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="persisted-service",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert repository.get_run(run.run_id) == run

    result = service.step_run(run.run_id, confidence=0.7)

    assert result.order is not None
    assert result.fill is not None
    assert result.ledger_entry is not None
    assert repository.get_run(run.run_id) == result.run
    assert repository.list_observation_snapshots(run.run_id) == [result.observation]
    assert repository.list_agent_runs(run.run_id) == [result.agent_run]
    assert repository.list_agent_messages(result.agent_run.agent_run_id) == list(
        result.agent_messages
    )
    assert repository.list_decisions(run.run_id) == [result.decision]
    assert repository.get_latest_risk_review(run.run_id) == result.risk_review
    assert repository.list_orders(run.run_id) == [result.order]
    assert repository.list_fills(run.run_id) == [result.fill]
    assert repository.list_positions(run.run_id) == list(result.positions)
    assert repository.list_ledger_entries(run.run_id) == [result.ledger_entry]
    assert repository.list_portfolio_snapshots(run.run_id) == [
        result.portfolio_snapshot
    ]
    assert repository.list_metric_snapshots(run.run_id) == [result.metric_snapshot]


def test_service_creates_decision_reviews_and_memory_entries() -> None:
    """Verify service creates posterior review and memory artifacts."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="review",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(run.run_id, confidence=0.7)

    review = service.create_decision_review(
        decision_id=result.decision.decision_id,
        horizon="1h",
        realized_return=Decimal("0.01"),
        max_adverse_excursion=Decimal("-0.002"),
        max_favorable_excursion=Decimal("0.014"),
        was_correct_directionally=True,
        error_tags=[],
        reviewer_summary="Decision remained directionally correct.",
    )
    memory = service.create_memory_entry(
        run_id=run.run_id,
        decision_id=result.decision.decision_id,
        memory_type="decision",
        summary="Decision review memory.",
        content={"review_id": str(review.review_id)},
        tags=["posterior_review"],
    )

    assert service.list_decision_reviews(result.decision.decision_id) == [review]
    assert service.list_memory_entries(run.run_id) == [memory]
    assert repository.list_decision_reviews(result.decision.decision_id) == [review]
    assert repository.list_memory_entries(run.run_id) == [memory]


def test_service_creates_reports_and_updates_alerts() -> None:
    """Verify service creates reports and alert workflow artifacts."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="reporting",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    service.step_run(run.run_id, confidence=0.7)

    report = service.create_simulation_report(run.run_id)
    alert = service.create_alert(
        run_id=run.run_id,
        category="drawdown",
        severity="warning",
        message="Drawdown near threshold.",
    )
    updated_alert = service.update_alert_status(
        run_id=run.run_id,
        alert_id=alert.alert_id,
        status="acknowledged",
    )

    activity = report.sections["activity"]
    assert isinstance(activity, dict)
    assert activity["decision_count"] == 1
    assert service.list_reports(run.run_id) == [report]
    assert updated_alert.status == "acknowledged"
    assert service.list_alerts(run.run_id) == [updated_alert]
    assert repository.list_reports(run.run_id) == [report]
    assert repository.list_alerts(run.run_id) == [updated_alert]


def test_service_rejects_memory_for_decision_from_another_run() -> None:
    """Verify memory entries cannot reference decisions from another run."""

    service = SimulationService(Settings())
    first_run = service.create_run(
        name="first",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second_run = service.create_run(
        name="second",
        symbols=["ETHUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(first_run.run_id, confidence=0.7)

    with pytest.raises(ValueError, match="must belong to the run"):
        service.create_memory_entry(
            run_id=second_run.run_id,
            decision_id=result.decision.decision_id,
            memory_type="decision",
            summary="Invalid cross-run memory.",
            content={},
            tags=[],
        )


def test_replay_backed_service_uses_replay_candle_as_simulated_time() -> None:
    """Verify replay-backed runs consume imported candles without lookahead."""

    repository = create_test_repository()
    candle = create_replay_candle()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="replay",
        symbols=["BTCUSDT"],
        replay_candles=[candle],
    )

    result = service.step_run(run.run_id, confidence=0.7)

    assert run.mode == "historical_replay"
    assert run.start_sim_time == candle.open_time
    assert result.candle == candle
    assert result.event.simulated_time == candle.as_of
    assert result.run.current_sim_time == candle.as_of
    assert repository.list_candles(run.run_id) == [candle]


def test_replay_backed_service_marks_run_completed_when_exhausted() -> None:
    """Verify replay exhaustion updates run lifecycle state."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="short-replay",
        symbols=["BTCUSDT"],
        replay_candles=[create_replay_candle()],
    )
    service.step_run(run.run_id)

    with pytest.raises(MarketReplayExhausted):
        service.step_run(run.run_id)

    assert service.get_run(run.run_id).status == "completed"
