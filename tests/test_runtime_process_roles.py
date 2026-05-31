"""Tests for scheduler and worker process role helpers."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from tiko.domain.account import SimAccount
from tiko.domain.market import Candle
from tiko.domain.runtime import BackgroundJob
from tiko.domain.simulation import SimulationRun
from tiko.runtime.scheduler import run_scheduler_once
from tiko.services.runtime import RuntimeService
from tiko.workers import (
    build_worker_definitions,
    process_worker_jobs,
    record_worker_heartbeats,
)


def create_rl_run() -> SimulationRun:
    """Create a simulation run payload for RL worker tests.

    Returns:
        Simulation run fixture.
    """

    account = SimAccount(
        account_id=uuid4(),
        name="rl-worker-account",
        initial_equity=Decimal("100000"),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
    )
    return SimulationRun(
        run_id=uuid4(),
        name="rl-worker-run",
        status="created",
        mode="historical_replay",
        account=account,
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        current_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        config={},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_rl_candles() -> list[Candle]:
    """Create point-in-time candles for RL worker tests.

    Returns:
        Ordered candle fixtures.
    """

    first_time = datetime(2026, 1, 1, 1, tzinfo=UTC)
    second_time = first_time + timedelta(hours=1)
    return [
        Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=first_time - timedelta(hours=1),
            close_time=first_time,
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("100"),
            volume=Decimal("10"),
            source="rl-worker-test",
            as_of=first_time,
            created_at=first_time,
        ),
        Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=first_time,
            close_time=second_time,
            open=Decimal("100"),
            high=Decimal("112"),
            low=Decimal("99"),
            close=Decimal("110"),
            volume=Decimal("12"),
            source="rl-worker-test",
            as_of=second_time,
            created_at=second_time,
        ),
    ]


def test_scheduler_once_reports_queued_work_without_worker() -> None:
    """Verify one scheduler tick runs watchdog checks."""

    service = RuntimeService()
    service.create_job(
        job_type="experiment_run",
        resource_type="experiment",
        resource_id="experiment-1",
        payload={},
    )

    report = run_scheduler_once(service)

    assert report.worker_status == "missing"
    assert report.queued_job_count == 1
    assert "queued_work_without_healthy_worker" in {
        check.code for check in report.checks
    }


def test_runtime_job_lifecycle_claims_only_eligible_jobs() -> None:
    """Verify runtime jobs move through claim and completion states."""

    service = RuntimeService()
    agent_job = service.create_job(
        job_type="agent_inference",
        resource_type="agent_run",
        resource_id="agent-run-1",
        payload={},
    )
    experiment_job = service.create_job(
        job_type="experiment_run",
        resource_type="experiment",
        resource_id="experiment-1",
        payload={},
    )

    claimed_job = service.claim_next_job(
        worker_name="backtest-worker",
        job_types=("experiment_run",),
    )

    assert claimed_job is not None
    assert claimed_job.job_id == experiment_job.job_id
    assert claimed_job.status == "running"
    assert claimed_job.claimed_by == "backtest-worker"
    assert claimed_job.started_at is not None
    assert service.get_job(agent_job.job_id).status == "queued"

    completed_job = service.complete_job(
        claimed_job.job_id,
        result={"message": "completed"},
    )
    next_job = service.claim_next_job(
        worker_name="backtest-worker",
        job_types=("experiment_run",),
    )

    assert completed_job.status == "completed"
    assert completed_job.result == {"message": "completed"}
    assert completed_job.completed_at is not None
    assert next_job is None
    assert service.count_queued_jobs() == 1


def test_worker_process_roles_record_healthy_heartbeats() -> None:
    """Verify known worker roles register healthy runtime heartbeats."""

    service = RuntimeService()
    definitions = build_worker_definitions()

    heartbeats = record_worker_heartbeats(service, definitions)
    report = service.run_watchdog()

    assert {definition.worker_name for definition in definitions} == {
        "agent-worker",
        "backtest-worker",
        "rl-worker",
        "report-worker",
    }
    assert {heartbeat.worker_name for heartbeat in heartbeats} == {
        "agent-worker",
        "backtest-worker",
        "rl-worker",
        "report-worker",
    }
    assert report.worker_status == "healthy"
    assert report.checks[0].code == "runtime_healthy"


def test_worker_process_jobs_completes_eligible_runtime_jobs() -> None:
    """Verify a worker claims and completes matching queued jobs."""

    service = RuntimeService()
    agent_job = service.create_job(
        job_type="agent_inference",
        resource_type="agent_run",
        resource_id="agent-run-1",
        payload={},
    )
    experiment_job = service.create_job(
        job_type="experiment_run",
        resource_type="experiment",
        resource_id="experiment-1",
        payload={},
    )
    definition = next(
        definition
        for definition in build_worker_definitions()
        if definition.worker_name == "backtest-worker"
    )

    result = process_worker_jobs(service, definition, max_jobs=5)
    empty_result = process_worker_jobs(service, definition, max_jobs=5)
    completed_job = service.get_job(experiment_job.job_id)
    unrelated_job = service.get_job(agent_job.job_id)
    heartbeat = service.list_heartbeats()[0]

    assert result.worker_name == "backtest-worker"
    assert result.claimed_job_ids == (experiment_job.job_id,)
    assert result.completed_job_ids == (experiment_job.job_id,)
    assert result.failed_job_ids == ()
    assert result.remaining_queue_depth == 0
    assert empty_result.claimed_job_ids == ()
    assert completed_job.status == "completed"
    assert completed_job.result["job_type"] == "experiment_run"
    assert completed_job.claimed_by == "backtest-worker"
    assert unrelated_job.status == "queued"
    assert heartbeat.worker_name == "backtest-worker"
    assert heartbeat.event_queue_depth == 0


def test_rl_worker_processes_static_training_jobs() -> None:
    """Verify RL worker jobs run deterministic static policy training."""

    service = RuntimeService()
    run = create_rl_run()
    candles = create_rl_candles()
    job = service.create_job(
        job_type="rl_training",
        resource_type="model",
        resource_id="rl-model-1",
        payload={
            "run": run.model_dump(mode="json"),
            "candles": [candle.model_dump(mode="json") for candle in candles],
            "candidate_action_ids": [0, 3],
        },
    )
    definition = next(
        definition
        for definition in build_worker_definitions()
        if definition.worker_name == "rl-worker"
    )

    result = process_worker_jobs(service, definition, max_jobs=1)
    completed_job = service.get_job(job.job_id)

    assert result.claimed_job_ids == (job.job_id,)
    assert result.completed_job_ids == (job.job_id,)
    assert result.failed_job_ids == ()
    assert completed_job.status == "completed"
    assert completed_job.result["algorithm"] == "static_discrete_policy_search"
    assert completed_job.result["best_action_id"] == 3
    summary = completed_job.result["summary"]
    assert isinstance(summary, dict)
    metrics = summary["metrics"]
    assert isinstance(metrics, dict)
    assert summary["episode_count"] == 2
    assert metrics["best_target_weight"] == "0.50"


def test_worker_process_jobs_fails_handler_errors() -> None:
    """Verify handler errors fail claimed jobs."""

    def fail_job(job: BackgroundJob) -> dict[str, object]:
        """Raise a deterministic worker handler error.

        Args:
            job: Claimed runtime job.

        Returns:
            This test handler never returns.
        """

        raise RuntimeError(f"handler failed for {job.resource_id}")

    service = RuntimeService()
    job = service.create_job(
        job_type="experiment_run",
        resource_type="experiment",
        resource_id="experiment-1",
        payload={},
    )
    definition = next(
        definition
        for definition in build_worker_definitions()
        if definition.worker_name == "backtest-worker"
    )

    result = process_worker_jobs(
        service,
        definition,
        handlers={"experiment_run": fail_job},
    )
    failed_job = service.get_job(job.job_id)

    assert result.claimed_job_ids == (job.job_id,)
    assert result.completed_job_ids == ()
    assert result.failed_job_ids == (job.job_id,)
    assert failed_job.status == "failed"
    assert failed_job.error_message == "handler failed for experiment-1"
    assert failed_job.completed_at is not None
