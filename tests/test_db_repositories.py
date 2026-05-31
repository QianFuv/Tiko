"""Tests for SQLAlchemy simulation repositories."""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect

from tiko.core.config import Settings
from tiko.db import (
    SimulationRepository,
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
from tiko.domain.decision import DecisionReview
from tiko.domain.memory import MemoryEntry
from tiko.domain.model import ModelRegistryEntry
from tiko.domain.plugin import PluginManifest, PluginPermissions, PluginRegistryEntry
from tiko.domain.reporting import Alert, ReportArtifact
from tiko.plugins import validate_plugin_manifest
from tiko.services import SimulationService


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """Create an in-memory SQLite engine for repository tests.

    Yields:
        SQLAlchemy engine with all persistence tables created.
    """

    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    create_all_tables(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def repository(sqlite_engine: Engine) -> SimulationRepository:
    """Create a simulation repository for tests.

    Args:
        sqlite_engine: SQLite engine fixture.

    Returns:
        Simulation repository bound to the test database.
    """

    return SimulationRepository(create_session_factory(sqlite_engine))


def test_metadata_creates_expected_tables(sqlite_engine: Engine) -> None:
    """Verify ORM metadata creates the current architecture tables."""

    table_names = set(inspect(sqlite_engine).get_table_names())

    assert table_names == {
        "accounts",
        "alerts",
        "candles",
        "decision_reviews",
        "decisions",
        "fills",
        "market_events",
        "memory_entries",
        "model_registry",
        "orders",
        "plugin_registry",
        "risk_reviews",
        "reports",
        "simulation_runs",
    }


def test_repository_round_trips_run_and_updates_account(
    repository: SimulationRepository,
) -> None:
    """Verify a simulation run and updated account state round-trip exactly."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="persisted",
        symbols=["BTCUSDT", "ETHUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    repository.save_run(run)

    updated_account = run.account.model_copy(
        update={"cash_balance": Decimal("99999.10")}
    )
    updated_run = run.model_copy(
        update={"status": "running", "account": updated_account}
    )
    repository.save_run(updated_run)

    loaded_run = repository.get_run(run.run_id)
    assert loaded_run == updated_run
    assert repository.list_runs() == [updated_run]


def test_repository_persists_successful_step_artifacts(
    repository: SimulationRepository,
) -> None:
    """Verify a successful simulation step persists all generated artifacts."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="step",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(run.run_id, confidence=0.7)

    repository.save_step_result(result)

    assert result.order is not None
    assert result.fill is not None
    assert repository.get_run(run.run_id) == result.run
    assert repository.list_candles(run.run_id) == [result.candle]
    assert repository.list_market_events(run.run_id) == [result.event]
    assert repository.list_decisions(run.run_id) == [result.decision]
    assert repository.get_latest_risk_review(run.run_id) == result.risk_review
    assert repository.list_orders(run.run_id) == [result.order]
    assert repository.list_fills(run.run_id) == [result.fill]


def test_repository_persists_decision_reviews_and_memory_entries(
    repository: SimulationRepository,
) -> None:
    """Verify posterior reviews and memory entries round-trip."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="memory",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(run.run_id, confidence=0.7)
    repository.save_step_result(result)
    review = DecisionReview(
        review_id=result.risk_review.review_id,
        decision_id=result.decision.decision_id,
        run_id=run.run_id,
        horizon="1h",
        realized_return=Decimal("0.012"),
        max_adverse_excursion=Decimal("-0.004"),
        max_favorable_excursion=Decimal("0.018"),
        was_correct_directionally=True,
        error_tags=[],
        reviewer_summary="Decision remained directionally correct.",
        created_at_sim_time=result.run.current_sim_time,
    )
    entry = MemoryEntry(
        memory_id=result.event.event_id,
        run_id=run.run_id,
        decision_id=result.decision.decision_id,
        memory_type="decision",
        summary="Positive follow-through after review.",
        content={"horizon": "1h"},
        tags=["posterior_review"],
        available_at_sim_time=result.run.current_sim_time,
        created_at=result.run.created_at,
    )

    repository.save_decision_review(review)
    repository.save_memory_entry(entry)

    assert repository.list_decision_reviews(result.decision.decision_id) == [review]
    assert repository.list_memory_entries(run.run_id) == [entry]


def test_repository_persists_model_registry_entries(
    repository: SimulationRepository,
) -> None:
    """Verify model registry entries persist and round-trip."""

    entry = ModelRegistryEntry(
        model_id=uuid4(),
        name="baseline-rl",
        version="0.1.0",
        model_type="rl",
        algorithm="discrete_policy",
        training_dataset_id=uuid4(),
        validation_dataset_id=uuid4(),
        metrics={"reward": "0.12"},
        artifact_uri="memory://baseline-rl",
        status="draft",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    repository.save_model_registry_entry(entry)

    assert repository.get_model_registry_entry(entry.model_id) == entry
    assert repository.list_model_registry_entries() == [entry]


def test_repository_persists_plugin_registry_entries(
    repository: SimulationRepository,
) -> None:
    """Verify plugin registry entries persist and round-trip."""

    manifest = PluginManifest(
        name="synthetic_liquidity_shock_generator",
        version="0.1.0",
        plugin_type="event_generation",
        description="Generate synthetic liquidity shocks for simulations.",
        permissions=PluginPermissions(write_market_events=True),
        inputs=["run_id", "symbols"],
        output_schema="MarketEvent",
        tests=["test_schema_valid"],
    )
    entry = PluginRegistryEntry(
        plugin_id=uuid4(),
        manifest=manifest,
        sandbox_result=validate_plugin_manifest(manifest),
        status="validated",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    repository.save_plugin_registry_entry(entry)

    assert repository.get_plugin_registry_entry(entry.plugin_id) == entry
    assert repository.list_plugin_registry_entries() == [entry]


def test_repository_persists_reports_and_alerts(
    repository: SimulationRepository,
) -> None:
    """Verify report and alert artifacts persist and round-trip."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="reporting",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    repository.save_run(run)
    report = ReportArtifact(
        report_id=uuid4(),
        run_id=run.run_id,
        report_type="simulation",
        title="Simulation report",
        summary="No activity yet.",
        sections={"activity": {"decision_count": 0}},
        created_at_sim_time=run.current_sim_time,
        created_at=run.created_at,
    )
    alert = Alert(
        alert_id=uuid4(),
        run_id=run.run_id,
        category="drawdown",
        severity="warning",
        message="Drawdown near threshold.",
        status="open",
        created_at_sim_time=run.current_sim_time,
        created_at=run.created_at,
    )

    repository.save_report(report)
    repository.save_alert(alert)

    assert repository.list_reports(run.run_id) == [report]
    assert repository.list_alerts(run.run_id) == [alert]


def test_repository_persists_rejected_step_without_order_or_fill(
    repository: SimulationRepository,
) -> None:
    """Verify rejected risk decisions do not create order or fill records."""

    service = SimulationService(Settings(minimum_trade_confidence=0.55))
    run = service.create_run(
        name="rejected",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(run.run_id, confidence=0.2)

    repository.save_step_result(result)

    assert repository.list_decisions(run.run_id) == [result.decision]
    assert repository.get_latest_risk_review(run.run_id) == result.risk_review
    assert repository.list_orders(run.run_id) == []
    assert repository.list_fills(run.run_id) == []
