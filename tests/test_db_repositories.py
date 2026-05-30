"""Tests for SQLAlchemy simulation repositories."""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, inspect

from tiko.core.config import Settings
from tiko.db import (
    SimulationRepository,
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
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
        "candles",
        "decisions",
        "fills",
        "market_events",
        "orders",
        "risk_reviews",
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
