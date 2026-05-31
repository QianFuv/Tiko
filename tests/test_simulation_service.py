"""Tests for deterministic in-memory simulation service behavior."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

from tiko.core.config import Settings
from tiko.db import (
    SimulationRepository,
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
from tiko.domain.market import Candle
from tiko.domain.order import Fill
from tiko.domain.reporting import ReportArtifact
from tiko.domain.runtime import BackgroundJob
from tiko.services import (
    RealtimeFanoutService,
    ReportArtifactStore,
    ReportRenderService,
    SimulationService,
)
from tiko.simulation.replay import MarketReplayExhausted
from tiko.workers.agent_worker import handle_agent_inference_job


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


def create_service_fill(
    run_id: UUID,
    symbol: str,
    side: Literal["buy", "sell"],
    quantity: Decimal,
    price: Decimal,
    hour: int,
) -> Fill:
    """Create a deterministic fill for service accounting tests.

    Args:
        run_id: Simulation run identifier.
        symbol: Fill symbol.
        side: Fill side.
        quantity: Fill quantity.
        price: Fill price.
        hour: Simulated fill hour.

    Returns:
        Fill domain model.
    """

    return Fill(
        fill_id=uuid4(),
        order_id=uuid4(),
        run_id=run_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        fee=Decimal("0"),
        slippage_bps=Decimal("0"),
        filled_at_sim_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
    )


def create_completed_agent_inference_job(
    service: SimulationService, run_id: UUID
) -> BackgroundJob:
    """Create a completed agent inference worker job for service tests.

    Args:
        service: Simulation service containing the run.
        run_id: Simulation run identifier.

    Returns:
        Completed background job with worker trace artifacts.
    """

    observation = service.build_observation(run_id, "BTCUSDT")
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
    running_job = BackgroundJob(
        job_id=uuid4(),
        job_type="agent_inference",
        resource_type="agent_run",
        resource_id="agent-worker-trace",
        status="running",
        payload={
            "agent_type": "rule_based",
            "observation": observation.model_dump(mode="json"),
        },
        created_at=now,
        updated_at=now,
        started_at=now,
    )
    result = handle_agent_inference_job(running_job)
    return running_job.model_copy(
        update={
            "status": "completed",
            "result": result,
            "completed_at": now,
        }
    )


class FakeRedisPublisher:
    """Capture Redis-compatible publish calls for realtime fanout tests."""

    def __init__(self) -> None:
        """Initialize the fake publisher."""

        self.messages: list[tuple[str, str]] = []

    def ping(self) -> bool:
        """Return a successful connectivity result.

        Returns:
            Always `True` for tests.
        """

        return True

    def publish(self, channel: str, message: str) -> int:
        """Capture one published message.

        Args:
            channel: Redis Pub/Sub channel.
            message: Serialized message payload.

        Returns:
            Simulated subscriber count.
        """

        self.messages.append((channel, message))
        return 1


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
    assert result.orderbook_snapshot.symbol == "BTCUSDT"
    assert result.feature_snapshot.features["one_step_return"] == "0"
    assert result.observation.symbol == "BTCUSDT"
    assert result.observation.account == run.account
    assert result.observation.orderbook == result.orderbook_snapshot
    assert result.observation.features == result.feature_snapshot.features
    assert result.observation.positions == []
    assert result.observation.risk_limits == service.get_risk_limits(run.run_id)
    assert result.agent_run.decision_id == result.decision.decision_id
    assert [message.role for message in result.agent_messages] == [
        "system",
        "observation",
        "assistant",
        "critic",
    ]
    assert result.agent_messages[3].content["decision_id"] == str(
        result.decision.decision_id
    )
    assert result.agent_messages[3].content["invalidation_conditions"] == [
        "confidence_below_threshold"
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
    assert service.list_orderbook_snapshots(run.run_id) == [result.orderbook_snapshot]
    assert service.list_feature_snapshots(run.run_id) == [result.feature_snapshot]
    assert service.list_observation_snapshots(run.run_id) == [result.observation]
    assert service.list_agent_runs() == [result.agent_run]
    assert service.list_agent_messages(result.agent_run.agent_run_id) == list(
        result.agent_messages
    )
    assert service.list_positions(run.run_id) == list(result.positions)
    assert service.list_ledger_entries(run.run_id) == [result.ledger_entry]
    assert service.list_portfolio_snapshots(run.run_id) == [result.portfolio_snapshot]
    assert service.list_metric_snapshots(run.run_id) == [result.metric_snapshot]


def test_service_uses_configured_broker_fee_and_slippage() -> None:
    """Verify simulation fills use configured broker fee and slippage settings."""

    service = SimulationService(
        Settings(
            sim_broker_taker_fee_bps=Decimal("10"),
            sim_broker_slippage_bps=Decimal("5"),
        )
    )
    run = service.create_run(
        name="broker-config",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = service.step_run(run.run_id, confidence=0.7)

    assert result.fill is not None
    expected_price = (
        result.candle.close * Decimal("1.0005")
        if result.fill.side == "buy"
        else result.candle.close * Decimal("0.9995")
    )
    expected_fee = result.fill.quantity * result.fill.price * Decimal("10")
    expected_fee /= Decimal("10000")
    assert result.fill.slippage_bps == Decimal("5")
    assert result.fill.price == expected_price
    assert result.fill.fee == expected_fee


def test_service_create_run_accepts_configured_simulation_fields() -> None:
    """Verify run creation stores configured simulation settings."""

    service = SimulationService(Settings())
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    end_time = start_time + timedelta(hours=1)

    run = service.create_run(
        name="configured",
        symbols=["BTCUSDT"],
        start_sim_time=start_time,
        mode="live_simulated_clock",
        end_sim_time=end_time,
        speed_multiplier=Decimal("3"),
        timeframe="15m",
        decision_interval="30m",
    )
    result = service.step_run(run.run_id, confidence=0.7)

    assert run.mode == "live_simulated_clock"
    assert run.end_sim_time == end_time
    assert run.speed_multiplier == Decimal("3")
    assert run.config["timeframe"] == "15m"
    assert run.config["decision_interval"] == "30m"
    assert result.run.status == "completed"

    with pytest.raises(ValueError, match="end_sim_time"):
        service.create_run(
            name="invalid-end",
            symbols=["BTCUSDT"],
            start_sim_time=start_time,
            end_sim_time=start_time,
        )


def test_simulation_steps_size_orders_against_existing_target() -> None:
    """Verify repeated target steps do not duplicate full target orders."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="target-delta",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    first_result = service.step_run(run.run_id, confidence=0.7)
    second_result = service.step_run(run.run_id, confidence=0.7)

    assert first_result.fill is not None
    first_notional = first_result.fill.quantity * first_result.fill.price
    second_notional = (
        second_result.fill.quantity * second_result.fill.price
        if second_result.fill is not None
        else Decimal("0")
    )
    assert second_notional < first_notional / Decimal("10")


def test_live_clock_advances_running_runs_by_speed_multiplier() -> None:
    """Verify live clock ticks advance running runs when steps are due."""

    service = SimulationService(Settings())
    run_start = datetime(2026, 1, 1, tzinfo=UTC)
    wall_start = datetime(2026, 1, 2, tzinfo=UTC)
    run = service.create_run(
        name="live-clock",
        symbols=["BTCUSDT"],
        start_sim_time=run_start,
    )
    service.update_run_speed(run.run_id, Decimal("10"))
    service.update_run_status(run.run_id, "running")

    first_tick = service.advance_running_runs(now=wall_start)
    early_tick = service.advance_running_runs(now=wall_start + timedelta(seconds=359))
    due_tick = service.advance_running_runs(now=wall_start + timedelta(seconds=360))
    next_due_tick = service.advance_running_runs(
        now=wall_start + timedelta(seconds=720)
    )

    assert first_tick == []
    assert early_tick == []
    assert len(due_tick) == 1
    assert due_tick[0].run.current_sim_time == run_start + timedelta(hours=1)
    assert len(next_due_tick) == 1
    assert next_due_tick[0].run.current_sim_time == run_start + timedelta(hours=2)


def test_live_clock_skips_paused_runs_and_rebaselines_on_resume() -> None:
    """Verify paused runs do not accumulate live clock advancement."""

    service = SimulationService(Settings())
    run_start = datetime(2026, 1, 1, tzinfo=UTC)
    wall_start = datetime(2026, 1, 2, tzinfo=UTC)
    run = service.create_run(
        name="live-clock-pause",
        symbols=["BTCUSDT"],
        start_sim_time=run_start,
    )
    service.update_run_speed(run.run_id, Decimal("10"))
    service.update_run_status(run.run_id, "running")
    service.advance_running_runs(now=wall_start)

    service.update_run_status(run.run_id, "paused")
    paused_tick = service.advance_running_runs(now=wall_start + timedelta(seconds=720))
    service.update_run_status(run.run_id, "running")
    resumed_baseline_tick = service.advance_running_runs(
        now=wall_start + timedelta(seconds=720)
    )
    resumed_due_tick = service.advance_running_runs(
        now=wall_start + timedelta(seconds=1080)
    )

    assert paused_tick == []
    assert resumed_baseline_tick == []
    assert len(resumed_due_tick) == 1
    assert resumed_due_tick[0].run.current_sim_time == run_start + timedelta(hours=1)


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


def test_synthetic_seed_controls_generated_candles() -> None:
    """Verify synthetic candle output is deterministic by configured seed."""

    first_service = SimulationService(Settings(synthetic_seed=100))
    second_service = SimulationService(Settings(synthetic_seed=100))
    third_service = SimulationService(Settings(synthetic_seed=101))
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    first_run = first_service.create_run("first-seed", ["BTCUSDT"], start_time)
    second_run = second_service.create_run("second-seed", ["BTCUSDT"], start_time)
    third_run = third_service.create_run("third-seed", ["BTCUSDT"], start_time)

    first_result = first_service.step_run(first_run.run_id)
    second_result = second_service.step_run(second_run.run_id)
    third_result = third_service.step_run(third_run.run_id)

    assert first_result.candle.close == second_result.candle.close
    assert first_result.candle.close != third_result.candle.close
    assert first_result.candle.close == Decimal("50093")
    assert third_result.candle.close == Decimal("50094")


def test_service_returns_latest_orderbook_snapshot_for_symbol() -> None:
    """Verify order book lookup returns latest read-only simulated snapshots."""

    service = SimulationService(Settings())
    first_run = service.create_run(
        name="first-orderbook",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second_run = service.create_run(
        name="second-orderbook",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 2, tzinfo=UTC),
    )
    first_step = service.step_run(first_run.run_id)
    latest_first_run_step = service.step_run(first_run.run_id)
    latest_second_run_step = service.step_run(second_run.run_id)

    assert (
        service.get_latest_orderbook_snapshot("BTCUSDT", first_run.run_id)
        == latest_first_run_step.orderbook_snapshot
    )
    assert (
        service.get_latest_orderbook_snapshot("BTCUSDT")
        == latest_second_run_step.orderbook_snapshot
    )
    assert (
        first_step.orderbook_snapshot.as_of
        < latest_first_run_step.orderbook_snapshot.as_of
    )
    assert service.get_latest_orderbook_snapshot("ETHUSDT", first_run.run_id) is None


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
    assert len(result.agent_messages) == 4
    assert result.order is None
    assert result.fill is None
    assert result.ledger_entry is None
    assert result.positions == ()
    assert result.metric_snapshot.metrics["fill_count"] == 0
    assert service.list_orders() == []
    assert service.list_fills() == []
    assert service.list_ledger_entries(run.run_id) == []
    assert service.list_portfolio_snapshots(run.run_id) == [result.portfolio_snapshot]


def test_daily_loss_circuit_blocks_after_prior_simulated_loss() -> None:
    """Verify prior simulated loss triggers the daily loss circuit breaker."""

    service = SimulationService(Settings(max_daily_loss=Decimal("0.00001")))
    run = service.create_run(
        name="daily-loss-circuit",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    first_result = service.step_run(run.run_id, confidence=0.7)

    second_result = service.step_run(run.run_id, confidence=0.7)

    assert first_result.risk_review.status == "approved"
    assert first_result.fill is not None
    assert second_result.risk_review.status == "circuit_blocked"
    assert second_result.risk_review.reasons == ["daily_loss_limit_exceeded"]
    assert second_result.order is None
    assert second_result.fill is None
    assert second_result.ledger_entry is None
    assert len(service.list_orders()) == 1
    assert len(service.list_fills()) == 1


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
    assert repository.list_orderbook_snapshots(run.run_id) == [
        result.orderbook_snapshot
    ]
    assert repository.list_feature_snapshots(run.run_id) == [result.feature_snapshot]
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
    realtime_events = repository.list_realtime_events(run.run_id)
    assert service.list_realtime_events(run.run_id) == realtime_events
    assert {str(event["topic"]) for event in realtime_events} == {
        "agent.run",
        "decision.created",
        "fill.created",
        "market.candle",
        "order.updated",
        "portfolio.updated",
        "risk.reviewed",
        "simulation.heartbeat",
        "simulation.status",
    }


def test_simulation_step_publishes_realtime_fanout_envelopes() -> None:
    """Verify simulation steps publish architecture realtime topics."""

    publisher = FakeRedisPublisher()
    fanout = RealtimeFanoutService(client=publisher, channel_prefix="tiko:test")
    service = SimulationService(Settings(), realtime_fanout=fanout)
    run = service.create_run(
        name="realtime-step",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    service.step_run(run.run_id, confidence=0.7)

    published_envelopes = [
        json.loads(message) for _channel, message in publisher.messages
    ]
    published_topics = {str(envelope["topic"]) for envelope in published_envelopes}
    assert published_topics == {
        "agent.run",
        "decision.created",
        "fill.created",
        "market.candle",
        "order.updated",
        "portfolio.updated",
        "risk.reviewed",
        "simulation.heartbeat",
        "simulation.status",
    }
    assert all(
        channel.startswith(f"tiko:test:{run.run_id}:")
        for channel, _message in publisher.messages
    )
    assert len(service.list_realtime_fanout_receipts()) == 9
    assert all(receipt.published for receipt in service.list_realtime_fanout_receipts())
    assert {
        str(event["event_id"]) for event in service.list_realtime_events(run.run_id)
    } == {str(envelope["event_id"]) for envelope in published_envelopes}
    heartbeat = next(
        envelope
        for envelope in published_envelopes
        if envelope["topic"] == "simulation.heartbeat"
    )
    assert heartbeat["payload"]["run_id"] == str(run.run_id)
    assert heartbeat["payload"]["event_queue_depth"] == 0
    assert heartbeat["payload"]["worker_status"] == "healthy"


def test_rejected_simulation_steps_skip_order_fill_fanout_topics() -> None:
    """Verify rejected steps publish only artifacts that exist."""

    publisher = FakeRedisPublisher()
    fanout = RealtimeFanoutService(client=publisher, channel_prefix="tiko:test")
    service = SimulationService(
        Settings(minimum_trade_confidence=0.55),
        realtime_fanout=fanout,
    )
    run = service.create_run(
        name="rejected-realtime-step",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    service.step_run(run.run_id, confidence=0.2)

    published_topics = {
        str(json.loads(message)["topic"]) for _channel, message in publisher.messages
    }
    assert "order.updated" not in published_topics
    assert "fill.created" not in published_topics
    assert published_topics == {
        "agent.run",
        "decision.created",
        "market.candle",
        "portfolio.updated",
        "risk.reviewed",
        "simulation.heartbeat",
        "simulation.status",
    }
    assert len(service.list_realtime_fanout_receipts()) == 7
    assert len(service.list_realtime_events(run.run_id)) == 7


def test_simulation_step_without_fanout_keeps_existing_behavior() -> None:
    """Verify the optional fanout path stays disabled by default."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="no-realtime-step",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = service.step_run(run.run_id, confidence=0.7)

    assert result.order is not None
    assert result.fill is not None
    assert service.list_orders() == [result.order]
    assert service.list_fills() == [result.fill]
    assert service.list_realtime_fanout_receipts() == []
    assert len(service.list_realtime_events(run.run_id)) == 9


def test_repository_backed_step_persists_realtime_events() -> None:
    """Verify repository-backed steps persist canonical realtime envelopes."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="persisted-realtime-events",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = service.step_run(run.run_id, confidence=0.7)

    realtime_events = service.list_realtime_events(run.run_id)
    payloads: list[dict[str, object]] = []
    for event in realtime_events:
        payload = event["payload"]
        if isinstance(payload, dict):
            payloads.append(payload)
    assert repository.list_realtime_events(run.run_id) == realtime_events
    assert len(realtime_events) == 9
    assert str(result.decision.decision_id) in {
        str(payload.get("decision_id")) for payload in payloads
    }


def test_manual_market_events_persist_and_publish_realtime_envelopes() -> None:
    """Verify manual market event injection emits canonical realtime envelopes."""

    repository = create_test_repository()
    publisher = FakeRedisPublisher()
    fanout = RealtimeFanoutService(client=publisher, channel_prefix="tiko:test")
    service = SimulationService(
        Settings(), repository=repository, realtime_fanout=fanout
    )
    run = service.create_run(
        name="manual-realtime-events",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    news_event = service.inject_market_event(
        run_id=run.run_id,
        type_="news_event",
        symbol="BTCUSDT",
        payload={"headline": "Synthetic macro headline."},
        source="manual",
        confidence=1.0,
        simulated_time=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
    )
    candle_event = service.inject_market_event(
        run_id=run.run_id,
        type_="candle_closed",
        symbol="BTCUSDT",
        payload={"close": "50000"},
        source="manual",
        confidence=1.0,
        simulated_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )

    realtime_events = service.list_realtime_events(run.run_id)
    published_envelopes = [
        json.loads(message) for _channel, message in publisher.messages
    ]
    events_by_topic = {
        str(event["topic"]): event
        for event in repository.list_realtime_events(run.run_id)
    }
    market_event_payload = events_by_topic["market.event"]["payload"]
    candle_event_payload = events_by_topic["market.candle"]["payload"]
    assert repository.list_realtime_events(run.run_id) == realtime_events
    assert set(events_by_topic) == {"market.candle", "market.event"}
    assert isinstance(market_event_payload, dict)
    assert isinstance(candle_event_payload, dict)
    assert market_event_payload["event_id"] == str(news_event.event_id)
    assert candle_event_payload["event_id"] == str(candle_event.event_id)
    assert published_envelopes == realtime_events
    assert [channel for channel, _message in publisher.messages] == [
        f"tiko:test:{run.run_id}:market.event",
        f"tiko:test:{run.run_id}:market.candle",
    ]
    assert len(service.list_realtime_fanout_receipts()) == 2
    assert all(receipt.published for receipt in service.list_realtime_fanout_receipts())


def test_service_applies_agent_inference_job_trace_state() -> None:
    """Verify completed agent inference jobs update service trace state."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="agent-worker-trace",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    job = create_completed_agent_inference_job(service, run.run_id)

    trace = service.apply_agent_inference_job(job)
    second_trace = service.apply_agent_inference_job(job)

    assert trace == second_trace
    assert (
        str(service.list_observation_snapshots(run.run_id)[0].observation_id)
        == (trace.messages[1].content["observation_id"])
    )
    assert service.list_decisions() == [trace.decision]
    assert service.list_agent_runs() == [trace.agent_run]
    assert service.list_agent_messages(trace.agent_run.agent_run_id) == trace.messages
    assert trace.risk_review is None
    assert trace.order is None
    assert trace.fill is None


def test_service_rejects_invalid_agent_inference_jobs() -> None:
    """Verify agent inference reconciliation rejects invalid job payloads."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="invalid-agent-worker-trace",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    job = create_completed_agent_inference_job(service, run.run_id)
    wrong_type_job = job.model_copy(update={"job_type": "report_generation"})
    failed_job = job.model_copy(update={"status": "failed"})
    result = dict(job.result)
    agent_run_value = result["agent_run"]
    assert isinstance(agent_run_value, dict)
    agent_run = dict(agent_run_value)
    agent_run["decision_id"] = str(uuid4())
    result["agent_run"] = agent_run
    mismatch_job = job.model_copy(update={"result": result})

    with pytest.raises(ValueError, match="Only agent_inference"):
        service.apply_agent_inference_job(wrong_type_job)
    with pytest.raises(ValueError, match="Only completed"):
        service.apply_agent_inference_job(failed_job)
    with pytest.raises(ValueError, match="decision_id"):
        service.apply_agent_inference_job(mismatch_job)
    assert service.list_decisions() == []


def test_repository_backed_service_persists_agent_inference_job_trace() -> None:
    """Verify agent inference job traces persist through the repository."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="persisted-agent-worker-trace",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    job = create_completed_agent_inference_job(service, run.run_id)

    trace = service.apply_agent_inference_job(job)

    assert repository.list_observation_snapshots(run.run_id)[0].run_id == run.run_id
    assert repository.list_decisions(run.run_id) == [trace.decision]
    assert repository.list_agent_runs(run.run_id) == [trace.agent_run]
    assert (
        repository.list_agent_messages(trace.agent_run.agent_run_id) == trace.messages
    )


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


def test_decision_report_includes_trace_and_posterior_sections() -> None:
    """Verify decision reports include trace and posterior review sections."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="decision-report",
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
        error_tags=["late_entry"],
        reviewer_summary="Decision remained directionally correct.",
    )

    report = service.create_decision_report(result.decision.decision_id)

    observation = report.sections["observation"]
    final_trade_intent = report.sections["final_trade_intent"]
    agent_subreports = report.sections["agent_subreports"]
    critic_objections = report.sections["critic_objections"]
    posterior_reviews = report.sections["posterior_reviews"]
    posterior_performance = report.sections["posterior_performance"]
    assert isinstance(observation, dict)
    assert isinstance(final_trade_intent, dict)
    assert isinstance(agent_subreports, list)
    assert isinstance(critic_objections, list)
    assert isinstance(posterior_reviews, list)
    assert isinstance(posterior_performance, dict)
    assert observation["observation_id"] == str(result.observation.observation_id)
    assert final_trade_intent["decision_id"] == str(result.decision.decision_id)
    assert [subreport["role"] for subreport in agent_subreports] == [
        "system",
        "observation",
        "assistant",
        "critic",
    ]
    assert len(critic_objections) == 1
    critic_objection = critic_objections[0]
    assert isinstance(critic_objection, dict)
    critic_content = critic_objection["content"]
    assert isinstance(critic_content, dict)
    assert critic_content["decision_id"] == str(result.decision.decision_id)
    assert len(posterior_reviews) == 1
    posterior_review = posterior_reviews[0]
    assert isinstance(posterior_review, dict)
    assert posterior_review["review_id"] == str(review.review_id)
    latest_posterior = posterior_performance["latest"]
    assert isinstance(latest_posterior, dict)
    assert posterior_performance["review_count"] == 1
    assert posterior_performance["correct_direction_count"] == 1
    assert posterior_performance["error_tags"] == ["late_entry"]
    assert latest_posterior["review_id"] == str(review.review_id)
    assert latest_posterior["realized_return"] == "0.01"
    assert report.sections["review_conclusion"] == review.reviewer_summary
    assert report.sections["decision"] == result.decision.model_dump(mode="json")
    assert repository.list_reports(run.run_id) == [report]


def test_service_searches_memory_entries_by_query_and_time() -> None:
    """Verify memory retrieval ranks matches and respects availability time."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="memory-search",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    full_match = service.create_memory_entry(
        run_id=run.run_id,
        memory_type="decision",
        summary="Risk drawdown review recommended patience.",
        content={"symbol": "BTCUSDT", "outcome": "adverse excursion"},
        tags=["risk", "drawdown"],
    )
    partial_match = service.create_memory_entry(
        run_id=run.run_id,
        memory_type="regime",
        summary="Risk budget tightened during quiet liquidity.",
        content={"symbol": "BTCUSDT"},
        tags=["risk"],
    )
    future_match = service.create_memory_entry(
        run_id=run.run_id,
        memory_type="failure",
        summary="Risk drawdown future event.",
        content={"symbol": "BTCUSDT"},
        tags=["risk", "drawdown"],
        available_at_sim_time=run.current_sim_time + timedelta(hours=1),
    )

    results = service.search_memory_entries(
        run_id=run.run_id,
        query="risk drawdown",
        as_of=run.current_sim_time,
        limit=5,
    )
    limited_results = service.search_memory_entries(
        run_id=run.run_id,
        query="risk drawdown",
        as_of=run.current_sim_time,
        limit=1,
    )
    no_match_results = service.search_memory_entries(
        run_id=run.run_id,
        query="unmatched",
        as_of=run.current_sim_time,
    )

    assert [result.entry.memory_id for result in results] == [
        full_match.memory_id,
        partial_match.memory_id,
    ]
    assert results[0].score == 1.0
    assert results[0].matched_terms == ["risk", "drawdown"]
    assert results[1].score == 0.5
    assert limited_results[0].entry.memory_id == full_match.memory_id
    assert no_match_results == []
    assert future_match.memory_id not in {result.entry.memory_id for result in results}
    with pytest.raises(ValueError, match="query"):
        service.search_memory_entries(run.run_id, " ")
    with pytest.raises(ValueError, match="limit"):
        service.search_memory_entries(run.run_id, "risk", limit=0)


def test_step_observation_uses_prior_positions_and_available_memory() -> None:
    """Verify step observations contain prior portfolio and available memory."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="context",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    first_result = service.step_run(run.run_id, confidence=0.7)
    memory = service.create_memory_entry(
        run_id=run.run_id,
        memory_type="decision",
        summary="First fill stayed inside risk budget.",
        content={"decision_id": str(first_result.decision.decision_id)},
        tags=["posterior_review"],
        available_at_sim_time=first_result.run.current_sim_time,
        decision_id=first_result.decision.decision_id,
    )

    second_result = service.step_run(run.run_id, confidence=0.7)

    assert first_result.observation.positions == []
    assert second_result.observation.account == first_result.run.account
    assert second_result.observation.positions == list(first_result.positions)
    assert second_result.observation.memory == [memory]
    assert second_result.observation.orderbook == second_result.orderbook_snapshot
    assert second_result.observation.features == second_result.feature_snapshot.features


def test_step_marks_positions_and_account_to_market() -> None:
    """Verify simulation steps mark positions and account equity to market."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="mark-accounting",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = service.step_run(run.run_id, confidence=0.7)

    position = result.positions[0]
    expected_unrealized_pnl = (
        position.mark_price - position.avg_entry_price
    ) * position.quantity
    expected_total_equity = result.run.account.cash_balance + position.notional
    expected_drawdown = (
        expected_total_equity - result.run.account.initial_equity
    ) / result.run.account.initial_equity

    assert position.mark_price == result.candle.close
    assert position.notional == position.quantity * result.candle.close
    assert position.unrealized_pnl == expected_unrealized_pnl
    assert result.run.account.unrealized_pnl == expected_unrealized_pnl
    assert result.run.account.total_equity == expected_total_equity
    assert result.run.account.max_drawdown == expected_drawdown
    assert result.portfolio_snapshot.total_equity == expected_total_equity
    assert result.portfolio_snapshot.unrealized_pnl == expected_unrealized_pnl
    assert result.portfolio_snapshot.max_drawdown == expected_drawdown


def test_service_derives_reduced_position_from_fill_accounting() -> None:
    """Verify service position derivation preserves cost basis after reductions."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="reduced-position",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    state = service._get_state(run.run_id)
    as_of = datetime(2026, 1, 1, 3, tzinfo=UTC)
    state.fills = [
        create_service_fill(
            run.run_id,
            "BTCUSDT",
            "buy",
            Decimal("2"),
            Decimal("100"),
            1,
        ),
        create_service_fill(
            run.run_id,
            "BTCUSDT",
            "sell",
            Decimal("0.5"),
            Decimal("110"),
            2,
        ),
    ]

    positions = service._derive_positions(
        state,
        mark_prices={"BTCUSDT": Decimal("110")},
        as_of=as_of,
    )

    assert len(positions) == 1
    position = positions[0]
    assert position.side == "long"
    assert position.quantity == Decimal("1.5")
    assert position.avg_entry_price == Decimal("100")
    assert position.realized_pnl == Decimal("5.0")
    assert position.unrealized_pnl == Decimal("15.0")
    assert position.updated_at_sim_time == as_of


def test_service_derives_liquidation_prices_for_positions() -> None:
    """Verify derived positions expose deterministic liquidation prices."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="liquidation-prices",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    state = service._get_state(run.run_id)
    state.fills = [
        create_service_fill(
            run.run_id,
            "BTCUSDT",
            "buy",
            Decimal("1"),
            Decimal("100"),
            1,
        )
    ]
    long_position = service._derive_positions(state)[0]
    state.fills = [
        create_service_fill(
            run.run_id,
            "BTCUSDT",
            "sell",
            Decimal("1"),
            Decimal("100"),
            2,
        )
    ]
    short_position = service._derive_positions(state)[0]

    assert long_position.side == "long"
    assert long_position.liquidation_price == Decimal("0")
    assert short_position.side == "short"
    assert short_position.liquidation_price == Decimal("200")


def test_mark_account_to_market_sets_liquidated_status() -> None:
    """Verify exhausted raw marked equity liquidates the simulated account."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="liquidation-status",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    state = service._get_state(run.run_id)
    state.fills = [
        create_service_fill(
            run.run_id,
            "BTCUSDT",
            "sell",
            Decimal("1"),
            Decimal("100"),
            1,
        )
    ]
    positions = service._derive_positions(
        state,
        mark_prices={"BTCUSDT": Decimal("250")},
    )
    small_account = run.account.model_copy(
        update={
            "initial_equity": Decimal("100"),
            "cash_balance": Decimal("100"),
            "total_equity": Decimal("100"),
        }
    )

    marked_account = service._mark_account_to_market(small_account, positions)

    assert marked_account.status == "liquidated"
    assert marked_account.total_equity == Decimal("0")
    assert marked_account.max_drawdown == Decimal("-1")


def test_step_applies_configured_funding_to_open_positions() -> None:
    """Verify configured funding creates separate ledger and account deltas."""

    service = SimulationService(Settings(synthetic_funding_rate=Decimal("0.001")))
    run = service.create_run(
        name="funding-accounting",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = service.step_run(run.run_id, confidence=0.7)

    assert result.funding_ledger_entry is not None
    funding_entry = result.funding_ledger_entry
    fill_entry = result.ledger_entry
    assert fill_entry is not None
    assert funding_entry.entry_type == "funding"
    assert funding_entry.fill_id is None
    assert funding_entry.cash_delta == -(
        result.positions[0].notional * Decimal("0.001")
    )
    assert funding_entry.realized_pnl_delta == funding_entry.cash_delta
    assert result.run.account.realized_pnl == (
        fill_entry.realized_pnl_delta + funding_entry.realized_pnl_delta
    )
    assert result.portfolio_snapshot.realized_pnl == result.run.account.realized_pnl
    assert result.metric_snapshot.metrics["cumulative_funding"] == str(
        funding_entry.cash_delta
    )
    assert service.list_ledger_entries(run.run_id) == [fill_entry, funding_entry]


def test_step_skips_funding_until_configured_interval() -> None:
    """Verify funding interval gating delays funding ledger entries."""

    service = SimulationService(
        Settings(
            synthetic_funding_rate=Decimal("0.001"),
            synthetic_funding_interval_steps=2,
        )
    )
    run = service.create_run(
        name="funding-interval",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    first_result = service.step_run(run.run_id, confidence=0.7)
    second_result = service.step_run(run.run_id, confidence=0.7)

    assert first_result.funding_ledger_entry is None
    assert second_result.funding_ledger_entry is not None
    assert second_result.funding_ledger_entry.entry_type == "funding"


def test_service_creates_reports_and_updates_alerts() -> None:
    """Verify service creates reports and alert workflow artifacts."""

    repository = create_test_repository()
    service = SimulationService(Settings(), repository=repository)
    run = service.create_run(
        name="reporting",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(run.run_id, confidence=0.7)
    alert = service.create_alert(
        run_id=run.run_id,
        category="drawdown",
        severity="warning",
        message="Drawdown near threshold.",
    )
    report = service.create_simulation_report(run.run_id)
    updated_alert = service.update_alert_status(
        run_id=run.run_id,
        alert_id=alert.alert_id,
        status="acknowledged",
    )

    activity = report.sections["activity"]
    timeline = report.sections["timeline"]
    dataset = report.sections["dataset"]
    equity_curve = report.sections["equity_curve"]
    drawdown_curve = report.sections["drawdown_curve"]
    position_curve = report.sections["position_curve"]
    trades = report.sections["trades"]
    key_metrics = report.sections["key_metrics"]
    risk_events = report.sections["risk_events"]
    agent_performance = report.sections["agent_performance"]
    error_attribution = report.sections["error_attribution"]
    assert isinstance(activity, dict)
    assert isinstance(timeline, dict)
    assert isinstance(dataset, dict)
    assert isinstance(equity_curve, list)
    assert isinstance(drawdown_curve, list)
    assert isinstance(position_curve, list)
    assert isinstance(trades, list)
    assert isinstance(key_metrics, dict)
    assert isinstance(risk_events, list)
    assert isinstance(agent_performance, dict)
    assert isinstance(error_attribution, dict)
    assert result.fill is not None
    assert activity["decision_count"] == 1
    assert timeline["start_sim_time"] == run.start_sim_time.isoformat()
    assert dataset["data_source"] == "synthetic"
    assert equity_curve[0]["total_equity"] == str(result.run.account.total_equity)
    assert drawdown_curve[0]["max_drawdown"] == str(result.run.account.max_drawdown)
    assert position_curve[0]["symbol"] == "BTCUSDT"
    assert trades[0]["fill_id"] == str(result.fill.fill_id)
    assert key_metrics["latest"]["fill_count"] == 1
    assert risk_events == []
    assert agent_performance["decision_count"] == 1
    assert error_attribution["alert_count"] == 1
    assert error_attribution["alerts"][0]["alert_id"] == str(alert.alert_id)
    assert service.list_reports(run.run_id) == [report]
    assert updated_alert.status == "acknowledged"
    assert service.list_alerts(run.run_id) == [updated_alert]
    assert repository.list_reports(run.run_id) == [report]
    assert repository.list_alerts(run.run_id) == [updated_alert]
    alert_realtime_events = [
        event
        for event in repository.list_realtime_events(run.run_id)
        if event["topic"] == "alert.created"
    ]
    alert_event_payload = alert_realtime_events[0]["payload"]
    assert len(alert_realtime_events) == 1
    assert isinstance(alert_event_payload, dict)
    assert alert_event_payload["alert_id"] == str(alert.alert_id)
    assert alert_event_payload["status"] == "open"


def test_report_renderer_creates_markdown_documents() -> None:
    """Verify structured reports render to deterministic Markdown."""

    service = SimulationService(Settings())
    renderer = ReportRenderService()
    run = service.create_run(
        name="rendering",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    service.step_run(run.run_id, confidence=0.7)
    report = service.create_simulation_report(run.run_id)

    rendered_report = renderer.render(report)

    assert rendered_report.report_id == report.report_id
    assert rendered_report.report_type == "simulation"
    assert rendered_report.format == "markdown"
    assert rendered_report.title == report.title
    assert rendered_report.content.startswith("# rendering simulation report")
    assert "- Report Type: simulation" in rendered_report.content
    assert "## Summary" in rendered_report.content
    assert "### Activity" in rendered_report.content
    assert '"decision_count": 1' in rendered_report.content


def test_report_renderer_handles_empty_sections() -> None:
    """Verify Markdown rendering works for reports without sections."""

    renderer = ReportRenderService()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    report = ReportArtifact(
        report_id=uuid4(),
        run_id=uuid4(),
        report_type="experiment",
        title="Empty experiment report",
        summary="No sections have been attached.",
        sections={},
        created_at_sim_time=created_at,
        created_at=created_at,
    )

    rendered_report = renderer.render(report)

    assert rendered_report.content == (
        f"# {report.title}\n"
        "\n"
        f"- Report ID: {report.report_id}\n"
        "- Report Type: experiment\n"
        f"- Run ID: {report.run_id}\n"
        f"- Created At: {created_at.isoformat()}\n"
        f"- Created At Sim Time: {created_at.isoformat()}\n"
        "\n"
        "## Summary\n"
        "\n"
        "No sections have been attached.\n"
    )


def test_report_artifact_store_writes_rendered_report(tmp_path: Path) -> None:
    """Verify rendered reports persist as local artifacts."""

    service = SimulationService(Settings())
    renderer = ReportRenderService()
    store = ReportArtifactStore(tmp_path)
    run = service.create_run(
        name="artifact-storage",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    service.step_run(run.run_id, confidence=0.7)
    report = service.create_simulation_report(run.run_id)
    rendered_report = renderer.render(report)

    artifact = store.store(rendered_report)
    artifact_path = tmp_path / "reports" / f"{report.report_id}.md"

    assert artifact.report_id == report.report_id
    assert artifact.format == "markdown"
    assert artifact.artifact_uri
    assert artifact.size_bytes == len(rendered_report.content.encode("utf-8"))
    assert artifact_path.read_text(encoding="utf-8") == rendered_report.content
    assert artifact_path.parent.name == "reports"


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
