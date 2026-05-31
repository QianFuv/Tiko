"""Tests for architecture domain schema validation."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tiko.core.auth import ROLE_PERMISSIONS, has_permission
from tiko.domain import (
    Asset,
    BackgroundJob,
    Candle,
    DatasetQualityReport,
    DatasetRecord,
    ExperimentRecord,
    Fill,
    OrderRequest,
    Principal,
    RiskReview,
    SimAccount,
    SimOrder,
    SimulationRun,
    TradeIntent,
    WatchdogReport,
    WorkerHeartbeat,
)


def current_time() -> datetime:
    """Return a stable timezone-aware timestamp for test fixtures.

    Returns:
        A UTC timestamp used by schema tests.
    """

    return datetime(2026, 1, 1, tzinfo=UTC)


def test_asset_preserves_decimal_constraints() -> None:
    """Verify asset schemas preserve decimal precision and reject bad sizes."""

    asset = Asset(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        market_type="perp",
        tick_size=Decimal("0.10"),
        lot_size=Decimal("0.001"),
        min_notional=Decimal("5"),
        fee_tier="standard",
        is_active=True,
    )

    assert asset.tick_size == Decimal("0.10")

    with pytest.raises(ValidationError):
        Asset(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            market_type="perp",
            tick_size=Decimal("0"),
            lot_size=Decimal("0.001"),
            min_notional=Decimal("5"),
            fee_tier="standard",
            is_active=True,
        )


def test_candle_rejects_negative_volume() -> None:
    """Verify candle volume cannot be negative."""

    with pytest.raises(ValidationError):
        Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=current_time(),
            close_time=current_time(),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("-1"),
            source="synthetic",
            as_of=current_time(),
            created_at=current_time(),
        )


def test_trade_intent_rejects_unknown_action() -> None:
    """Verify agent output is restricted to known structured actions."""

    with pytest.raises(ValidationError):
        TradeIntent.model_validate(
            {
                "decision_id": uuid4(),
                "run_id": uuid4(),
                "agent_id": "trader",
                "symbol": "BTCUSDT",
                "market_type": "perp",
                "action": "buy_now",
                "target_weight": Decimal("0.2"),
                "max_leverage": Decimal("1"),
                "confidence": 0.7,
                "expected_holding_period": "4h",
                "thesis": "Momentum continuation.",
                "evidence": [],
                "invalidation_conditions": [],
                "data_quality_score": 0.95,
                "created_at_sim_time": current_time(),
            }
        )


def test_order_and_fill_schemas_model_simulated_execution() -> None:
    """Verify order and fill schemas encode internal simulated execution only."""

    run_id = uuid4()
    account_id = uuid4()
    order_id = uuid4()
    request = OrderRequest(
        run_id=run_id,
        account_id=account_id,
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=Decimal("0.1"),
        submitted_at_sim_time=current_time(),
    )
    order = SimOrder(
        order_id=order_id,
        run_id=request.run_id,
        account_id=request.account_id,
        symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        quantity=request.quantity,
        status="filled",
        submitted_at_sim_time=request.submitted_at_sim_time,
        updated_at_sim_time=current_time(),
    )
    fill = Fill(
        fill_id=uuid4(),
        order_id=order.order_id,
        run_id=order.run_id,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        price=Decimal("100"),
        fee=Decimal("0.01"),
        slippage_bps=Decimal("2"),
        filled_at_sim_time=current_time(),
    )

    assert fill.quantity == request.quantity
    assert order.status == "filled"


def test_risk_review_and_simulation_run_are_validated() -> None:
    """Verify risk review and simulation run schemas enforce known states."""

    account = SimAccount(
        account_id=uuid4(),
        name="demo",
        initial_equity=Decimal("100000"),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
    )
    run = SimulationRun(
        run_id=uuid4(),
        name="demo-run",
        status="created",
        mode="synthetic_market",
        account=account,
        symbols=["BTCUSDT"],
        start_sim_time=current_time(),
        current_sim_time=current_time(),
        config={},
        created_at=current_time(),
    )
    review = RiskReview(
        review_id=uuid4(),
        decision_id=uuid4(),
        status="approved",
        original_target_weight=Decimal("0.1"),
        approved_target_weight=Decimal("0.1"),
        max_order_notional=Decimal("10000"),
        reasons=[],
        triggered_rules=[],
        created_at_sim_time=current_time(),
    )

    assert run.account.total_equity == Decimal("100000")
    assert review.status == "approved"

    with pytest.raises(ValidationError):
        RiskReview.model_validate(
            {
                "review_id": uuid4(),
                "decision_id": uuid4(),
                "status": "ignored",
                "original_target_weight": Decimal("0.1"),
                "approved_target_weight": Decimal("0.1"),
                "max_order_notional": Decimal("10000"),
                "reasons": [],
                "triggered_rules": [],
                "created_at_sim_time": current_time(),
            }
        )


def test_security_roles_preserve_read_only_viewer_boundary() -> None:
    """Verify security schemas keep viewers read-only and reject unknown roles."""

    viewer = Principal(user_id="viewer@example.test", role="viewer")

    assert has_permission(viewer, "observe") is True
    assert has_permission(viewer, "manage_simulations") is False
    assert "manage_simulations" not in ROLE_PERMISSIONS["viewer"]
    assert {
        permission
        for permissions in ROLE_PERMISSIONS.values()
        for permission in permissions
        if "trading" in permission
    } == set()

    with pytest.raises(ValidationError):
        Principal.model_validate({"user_id": "invalid@example.test", "role": "trader"})


def test_dataset_and_experiment_schemas_validate_research_state() -> None:
    """Verify research control-plane schemas constrain known states."""

    dataset_id = uuid4()
    dataset = DatasetRecord(
        dataset_id=dataset_id,
        name="BTCUSDT research candles",
        source="csv",
        source_uri="memory://candles.csv",
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        candle_count=1,
        status="validated",
        start_time=current_time(),
        end_time=current_time(),
        created_at=current_time(),
    )
    quality = DatasetQualityReport(
        dataset_id=dataset.dataset_id,
        total_records=1,
        error_count=0,
        warning_count=0,
        has_errors=False,
        issues=[],
    )
    experiment = ExperimentRecord(
        experiment_id=uuid4(),
        name="baseline walk-forward",
        kind="walk_forward",
        hypothesis="Momentum survives validation splits.",
        dataset_id=dataset.dataset_id,
        parameters={"splits": 3},
        status="queued",
        metrics={},
        created_at=current_time(),
        queued_at=current_time(),
    )

    assert quality.dataset_id == dataset_id
    assert experiment.dataset_id == dataset_id
    assert experiment.status == "queued"

    with pytest.raises(ValidationError):
        DatasetRecord.model_validate(dataset.model_dump() | {"status": "uploaded"})
    with pytest.raises(ValidationError):
        ExperimentRecord.model_validate(
            experiment.model_dump() | {"kind": "live_trade"}
        )


def test_runtime_schemas_validate_worker_and_job_state() -> None:
    """Verify runtime schemas constrain jobs, heartbeats, and reports."""

    job = BackgroundJob(
        job_id=uuid4(),
        job_type="experiment_run",
        resource_type="experiment",
        resource_id=str(uuid4()),
        status="queued",
        payload={"priority": "normal"},
        created_at=current_time(),
        updated_at=current_time(),
    )
    heartbeat = WorkerHeartbeat(
        heartbeat_id=uuid4(),
        worker_name="backtest-worker",
        worker_status="healthy",
        event_queue_depth=0,
        clock_lag_ms=10,
        last_seen_at=current_time(),
    )
    report = WatchdogReport(
        report_id=uuid4(),
        checked_at=current_time(),
        worker_status=heartbeat.worker_status,
        queued_job_count=1,
        unhealthy_workers=[],
        checks=[],
    )

    assert job.status == "queued"
    assert report.worker_status == "healthy"

    with pytest.raises(ValidationError):
        WorkerHeartbeat.model_validate(
            heartbeat.model_dump() | {"event_queue_depth": -1}
        )
    with pytest.raises(ValidationError):
        BackgroundJob.model_validate(job.model_dump() | {"job_type": "live_order"})
