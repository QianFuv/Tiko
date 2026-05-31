"""Tests for SQLAlchemy simulation repositories."""

import csv
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, inspect

from tiko.core.config import Settings
from tiko.db import (
    SimulationRepository,
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
from tiko.domain.dataset import DatasetQualityIssue, DatasetQualityReport, DatasetRecord
from tiko.domain.decision import DecisionReview
from tiko.domain.experiment import ExperimentRecord
from tiko.domain.market import Asset, Candle, MarketEvent
from tiko.domain.memory import MemoryEntry
from tiko.domain.model import ModelRegistryEntry
from tiko.domain.plugin import PluginManifest, PluginPermissions, PluginRegistryEntry
from tiko.domain.registry import ProjectRecord, SimulationDefinition, UserProfile
from tiko.domain.reporting import Alert, ReportArtifact
from tiko.domain.runtime import BackgroundJob
from tiko.domain.security import AuditLogEntry, Principal
from tiko.plugins import validate_plugin_manifest
from tiko.services import (
    AuditService,
    DatasetService,
    ExperimentService,
    ModelRegistryService,
    PluginRegistryService,
    SimulationService,
)


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


def sample_candle() -> Candle:
    """Create a normalized candle fixture.

    Returns:
        Candle domain model.
    """

    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("2.5"),
        quote_volume=Decimal("262.5"),
        source="fixture",
        as_of=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
    )


def sample_asset() -> Asset:
    """Create an asset fixture.

    Returns:
        Asset domain model.
    """

    return Asset(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        market_type="synthetic",
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.000001"),
        min_notional=Decimal("5"),
        fee_tier="simulated",
        is_active=True,
    )


def sample_dataset(dataset_id: UUID | None = None) -> DatasetRecord:
    """Create a dataset metadata fixture.

    Args:
        dataset_id: Optional dataset identifier.

    Returns:
        Dataset record domain model.
    """

    return DatasetRecord(
        dataset_id=dataset_id or uuid4(),
        name="fixture candles",
        source="csv",
        source_uri="memory://fixture.csv",
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        candle_count=1,
        status="validated",
        start_time=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
    )


def sample_quality_report(dataset_id: UUID) -> DatasetQualityReport:
    """Create a dataset quality report fixture.

    Args:
        dataset_id: Dataset identifier.

    Returns:
        Dataset quality report domain model.
    """

    return DatasetQualityReport(
        dataset_id=dataset_id,
        total_records=1,
        error_count=0,
        warning_count=1,
        has_errors=False,
        issues=[
            DatasetQualityIssue(
                index=0,
                severity="warning",
                code="fixture_warning",
                message="Fixture warning.",
                symbol="BTCUSDT",
                open_time="2026-01-01T00:00:00Z",
            )
        ],
    )


def sample_experiment(dataset_id: UUID) -> ExperimentRecord:
    """Create an experiment fixture.

    Args:
        dataset_id: Dataset identifier.

    Returns:
        Experiment record domain model.
    """

    return ExperimentRecord(
        experiment_id=uuid4(),
        name="baseline walk-forward",
        kind="walk_forward",
        hypothesis="Momentum survives validation splits.",
        dataset_id=dataset_id,
        parameters={"splits": 3},
        status="draft",
        metrics={},
        created_at=datetime(2026, 1, 1, 2, 0, tzinfo=UTC),
    )


def write_candle_csv(path: Path) -> None:
    """Write a one-row candle CSV fixture.

    Args:
        path: Destination CSV path.
    """

    row = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-01-01T01:00:00Z",
        "open": "100",
        "high": "110",
        "low": "90",
        "close": "105",
        "volume": "2.5",
        "quote_volume": "262.5",
        "source": "fixture",
        "as_of": "2026-01-01T01:00:00Z",
        "created_at": "2026-01-01T01:00:00Z",
    }
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def test_metadata_creates_expected_tables(sqlite_engine: Engine) -> None:
    """Verify ORM metadata creates the current architecture tables."""

    table_names = set(inspect(sqlite_engine).get_table_names())

    assert table_names == {
        "accounts",
        "agent_messages",
        "agent_runs",
        "alerts",
        "assets",
        "audit_logs",
        "candles",
        "dataset_candles",
        "dataset_quality_reports",
        "datasets",
        "decision_reviews",
        "decisions",
        "experiments",
        "feature_snapshots",
        "fills",
        "ledger_entries",
        "market_events",
        "memory_entries",
        "metric_snapshots",
        "model_registry",
        "orders",
        "observation_snapshots",
        "orderbook_snapshots",
        "plugin_registry",
        "portfolio_snapshots",
        "positions",
        "projects",
        "risk_reviews",
        "reports",
        "simulations",
        "simulation_runs",
        "users",
    }


def test_repository_persists_audit_logs(repository: SimulationRepository) -> None:
    """Verify audit log entries round-trip through the repository."""

    entry = AuditLogEntry(
        audit_id=uuid4(),
        user_id="operator@example.test",
        role="operator",
        action="simulation.start",
        resource_type="simulation_run",
        resource_id="run-1",
        metadata={"status": "running"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    repository.save_audit_log_entry(entry)

    assert repository.list_audit_log_entries() == [entry]


def test_audit_service_writes_through_repository(
    repository: SimulationRepository,
) -> None:
    """Verify repository-backed audit service persists created entries."""

    service = AuditService(repository)
    principal = Principal(user_id="admin@example.test", role="admin")

    entry = service.record(
        principal=principal,
        action="dataset.upload",
        resource_type="dataset",
        resource_id="dataset-1",
        metadata={"source": "csv"},
    )

    assert service.list_entries() == [entry]
    assert repository.list_audit_log_entries() == [entry]


def test_repository_persists_control_plane_registry(
    repository: SimulationRepository,
) -> None:
    """Verify user, project, and simulation definition records round-trip."""

    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    user = UserProfile(
        user_id="researcher@example.test",
        role="researcher",
        display_name="Researcher",
        is_disabled=False,
        created_at=created_at,
    )
    project = ProjectRecord(
        project_id=uuid4(),
        name="Research workspace",
        owner_user_id=user.user_id,
        description="Simulation research namespace.",
        created_at=created_at,
    )
    definition = SimulationDefinition(
        simulation_id=uuid4(),
        project_id=project.project_id,
        name="BTC synthetic replay",
        mode="synthetic_market",
        symbols=["BTCUSDT"],
        config={"speed_multiplier": "1"},
        created_at=created_at,
    )

    repository.save_user_profile(user)
    repository.save_project_record(project)
    repository.save_simulation_definition(definition)

    assert repository.get_user_profile(user.user_id) == user
    assert repository.list_user_profiles() == [user]
    assert repository.get_project_record(project.project_id) == project
    assert repository.list_project_records() == [project]
    assert repository.get_simulation_definition(definition.simulation_id) == definition
    assert repository.list_simulation_definitions() == [definition]


def test_repository_persists_manual_market_events(
    repository: SimulationRepository,
) -> None:
    """Verify manually injected market events persist independently."""

    service = SimulationService(Settings())
    run = service.create_run(
        name="manual-event",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    event = MarketEvent(
        event_id=uuid4(),
        type="news_event",
        symbol="BTCUSDT",
        simulated_time=run.current_sim_time,
        payload={"headline": "Synthetic market shock."},
        source="manual",
        confidence=0.9,
    )
    repository.save_run(run)

    repository.save_market_event(run.run_id, event)

    assert repository.list_market_events(run.run_id) == [event]


def test_repository_persists_assets(repository: SimulationRepository) -> None:
    """Verify asset metadata round-trips through the repository."""

    asset = sample_asset()

    repository.save_asset(asset)

    assert repository.list_assets() == [asset]


def test_repository_persists_datasets(
    repository: SimulationRepository,
) -> None:
    """Verify dataset metadata, candles, and quality reports round-trip."""

    dataset = sample_dataset()
    candle = sample_candle()
    quality_report = sample_quality_report(dataset.dataset_id)

    repository.save_dataset(dataset, (candle,), quality_report)

    assert repository.get_dataset(dataset.dataset_id) == dataset
    assert repository.list_datasets() == [dataset]
    assert repository.get_dataset_quality_report(dataset.dataset_id) == quality_report
    assert repository.list_dataset_candles(dataset.dataset_id, limit=10) == [candle]
    assert repository.list_dataset_candles(dataset.dataset_id, limit=0) == []


def test_repository_persists_experiments(
    repository: SimulationRepository,
) -> None:
    """Verify research experiments round-trip through the repository."""

    dataset = sample_dataset()
    experiment = sample_experiment(dataset.dataset_id)
    repository.save_dataset(
        dataset, (sample_candle(),), sample_quality_report(dataset.dataset_id)
    )

    repository.save_experiment(experiment)

    assert repository.get_experiment(experiment.experiment_id) == experiment
    assert repository.list_experiments() == [experiment]


def test_dataset_service_writes_through_repository(
    repository: SimulationRepository, tmp_path: Path
) -> None:
    """Verify repository-backed dataset service persists uploads and validation."""

    path = tmp_path / "candles.csv"
    write_candle_csv(path)
    service = DatasetService(repository=repository)

    dataset = service.upload_dataset("BTC fixture", str(path))
    persisted_service = DatasetService(repository=repository)
    quality_report = persisted_service.validate_dataset(dataset.dataset_id)

    assert persisted_service.list_datasets() == [
        dataset.model_copy(update={"status": "validated"})
    ]
    assert persisted_service.get_dataset(dataset.dataset_id).name == "BTC fixture"
    assert persisted_service.get_quality_report(dataset.dataset_id) == quality_report
    assert persisted_service.list_candles(dataset.dataset_id, limit=1)[0].symbol == (
        "BTCUSDT"
    )


def test_experiment_service_writes_through_repository(
    repository: SimulationRepository,
) -> None:
    """Verify repository-backed experiment service persists lifecycle and reports."""

    dataset = sample_dataset()
    repository.save_dataset(
        dataset, (sample_candle(),), sample_quality_report(dataset.dataset_id)
    )
    service = ExperimentService(repository)
    experiment = service.create_experiment(
        name="baseline walk-forward",
        kind="walk_forward",
        hypothesis="Momentum survives validation splits.",
        dataset_id=dataset.dataset_id,
        parameters={"splits": 3},
    )
    persisted_service = ExperimentService(repository)

    job_id = uuid4()
    queued = persisted_service.queue_run(experiment.experiment_id, job_id=job_id)
    completed_job = BackgroundJob(
        job_id=job_id,
        job_type="experiment_run",
        resource_type="experiment",
        resource_id=str(experiment.experiment_id),
        status="completed",
        payload={},
        result={
            "backtest_summary": {"candle_count": 1},
            "returns_by_symbol": {"BTCUSDT": "0.05"},
        },
        created_at=datetime(2026, 1, 1, 2, 30, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, 2, 31, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 2, 31, tzinfo=UTC),
    )
    completed = persisted_service.apply_runtime_job(completed_job)
    report = persisted_service.create_experiment_report(experiment.experiment_id)

    assert persisted_service.list_experiments() == [completed]
    assert persisted_service.get_experiment(experiment.experiment_id) == completed
    assert queued.status == "queued"
    assert queued.metrics["queued"] is True
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert completed.metrics["completed"] is True
    assert completed.metrics["job_id"] == str(job_id)
    assert completed.metrics["returns_by_symbol"] == {"BTCUSDT": "0.05"}
    assert persisted_service.list_experiment_reports(experiment.experiment_id) == [
        report
    ]
    assert persisted_service.get_report(report.report_id) == report
    assert repository.get_report(report.report_id) == report


def test_experiment_service_applies_failed_runtime_jobs() -> None:
    """Verify failed runtime jobs update experiment failure state."""

    service = ExperimentService()
    experiment = service.create_experiment(
        name="failed backtest",
        kind="backtest",
        hypothesis="Runtime failures should be visible.",
        dataset_id=uuid4(),
        parameters={},
    )
    job_id = uuid4()
    service.queue_run(experiment.experiment_id, job_id=job_id)
    failed_job = BackgroundJob(
        job_id=job_id,
        job_type="experiment_run",
        resource_type="experiment",
        resource_id=str(experiment.experiment_id),
        status="failed",
        payload={},
        error_message="worker failed",
        created_at=datetime(2026, 1, 1, 3, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, 3, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 3, 1, tzinfo=UTC),
    )

    failed = service.apply_runtime_job(failed_job)
    invalid_job = failed_job.model_copy(update={"job_type": "report_generation"})

    assert failed.status == "failed"
    assert failed.completed_at is not None
    assert failed.metrics["failed"] is True
    assert failed.metrics["error_message"] == "worker failed"
    assert failed.metrics["job_id"] == str(job_id)
    with pytest.raises(ValueError, match="Only experiment_run"):
        service.apply_runtime_job(invalid_job)


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
    assert result.ledger_entry is not None
    assert repository.get_run(run.run_id) == result.run
    assert repository.list_candles(run.run_id) == [result.candle]
    assert repository.list_orderbook_snapshots(run.run_id) == [
        result.orderbook_snapshot
    ]
    assert repository.list_feature_snapshots(run.run_id) == [result.feature_snapshot]
    assert repository.list_market_events(run.run_id) == [result.event]
    assert repository.list_observation_snapshots(run.run_id) == [result.observation]
    assert repository.list_agent_runs(run.run_id) == [result.agent_run]
    assert repository.list_agent_messages(result.agent_run.agent_run_id) == list(
        result.agent_messages
    )
    assert repository.list_decisions(run.run_id) == [result.decision]
    assert repository.list_risk_reviews(run.run_id) == [result.risk_review]
    assert repository.get_latest_risk_review(run.run_id) == result.risk_review
    assert repository.list_orders(run.run_id) == [result.order]
    assert repository.list_fills(run.run_id) == [result.fill]
    assert repository.list_positions(run.run_id) == list(result.positions)
    assert repository.list_ledger_entries(run.run_id) == [result.ledger_entry]
    assert repository.list_portfolio_snapshots(run.run_id) == [
        result.portfolio_snapshot
    ]
    assert repository.list_metric_snapshots(run.run_id) == [result.metric_snapshot]


def test_repository_persists_funding_ledger_entries(
    repository: SimulationRepository,
) -> None:
    """Verify funding ledger entries persist separately from fill entries."""

    service = SimulationService(Settings(synthetic_funding_rate=Decimal("0.001")))
    run = service.create_run(
        name="funding-step",
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = service.step_run(run.run_id, confidence=0.7)

    repository.save_step_result(result)

    assert result.ledger_entry is not None
    assert result.funding_ledger_entry is not None
    ledger_entries = repository.list_ledger_entries(run.run_id)
    assert ledger_entries == [result.ledger_entry, result.funding_ledger_entry]
    assert ledger_entries[1].entry_type == "funding"


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


def test_model_registry_service_reads_through_repository(
    repository: SimulationRepository,
) -> None:
    """Verify repository-backed model service reads persisted entries."""

    service = ModelRegistryService(repository)
    entry = service.register_model(
        name="baseline-rl",
        version="0.1.0",
        model_type="rl",
        algorithm="discrete_policy",
        training_dataset_id=uuid4(),
        validation_dataset_id=uuid4(),
        metrics={"reward": "0.12"},
        artifact_uri="memory://baseline-rl",
        status="draft",
    )
    persisted_service = ModelRegistryService(repository)

    assert persisted_service.list_models() == [entry]
    assert persisted_service.get_model(entry.model_id) == entry
    promoted = persisted_service.promote_model(entry.model_id)
    assert promoted.status == "paper_enabled"
    assert ModelRegistryService(repository).get_model(entry.model_id) == promoted


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


def test_plugin_registry_service_reads_through_repository(
    repository: SimulationRepository,
) -> None:
    """Verify repository-backed plugin service reads persisted entries."""

    service = PluginRegistryService(repository)
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
    entry = service.register_plugin(manifest)
    persisted_service = PluginRegistryService(repository)

    assert persisted_service.list_plugins() == [entry]
    assert persisted_service.get_plugin(entry.plugin_id) == entry
    enabled = persisted_service.update_status(entry.plugin_id, "enabled")
    assert enabled.status == "enabled"
    assert PluginRegistryService(repository).get_plugin(entry.plugin_id) == enabled


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
    assert repository.list_orderbook_snapshots(run.run_id) == [
        result.orderbook_snapshot
    ]
    assert repository.list_feature_snapshots(run.run_id) == [result.feature_snapshot]
    assert repository.list_observation_snapshots(run.run_id) == [result.observation]
    assert repository.list_agent_runs(run.run_id) == [result.agent_run]
    assert repository.list_agent_messages(result.agent_run.agent_run_id) == list(
        result.agent_messages
    )
    assert repository.get_latest_risk_review(run.run_id) == result.risk_review
    assert repository.list_orders(run.run_id) == []
    assert repository.list_fills(run.run_id) == []
    assert repository.list_positions(run.run_id) == []
    assert repository.list_ledger_entries(run.run_id) == []
    assert repository.list_portfolio_snapshots(run.run_id) == [
        result.portfolio_snapshot
    ]
    assert repository.list_metric_snapshots(run.run_id) == [result.metric_snapshot]
