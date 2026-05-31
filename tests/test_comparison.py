"""Tests for deterministic replay comparison tooling."""

from datetime import UTC, datetime

from tiko.core.config import Settings
from tiko.services import SimulationService


def test_equivalent_runs_have_matching_fingerprints() -> None:
    """Verify equivalent deterministic runs produce matching fingerprints."""

    service = SimulationService(Settings())
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    first_run = service.create_run("first", ["BTCUSDT"], start_time)
    second_run = service.create_run("second", ["BTCUSDT"], start_time)
    service.step_run(first_run.run_id, confidence=0.7)
    service.step_run(second_run.run_id, confidence=0.7)

    comparison = service.compare_runs(first_run.run_id, second_run.run_id)

    assert comparison.fingerprints_match is True
    assert comparison.deltas["fill_count"] == 0
    assert comparison.deltas["total_equity"] == 0


def test_different_execution_outcomes_change_fingerprints() -> None:
    """Verify different risk outcomes produce different fingerprints."""

    service = SimulationService(Settings(minimum_trade_confidence=0.55))
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    approved_run = service.create_run("approved", ["BTCUSDT"], start_time)
    rejected_run = service.create_run("rejected", ["BTCUSDT"], start_time)
    service.step_run(approved_run.run_id, confidence=0.7)
    service.step_run(rejected_run.run_id, confidence=0.2)

    comparison = service.compare_runs(approved_run.run_id, rejected_run.run_id)

    assert comparison.fingerprints_match is False
    assert comparison.deltas["fill_count"] == -1
    assert comparison.candidate.fill_count == 0
