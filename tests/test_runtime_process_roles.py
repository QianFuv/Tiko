"""Tests for scheduler and worker process role helpers."""

from tiko.runtime.scheduler import run_scheduler_once
from tiko.services.runtime import RuntimeService
from tiko.workers import build_worker_definitions, record_worker_heartbeats


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
