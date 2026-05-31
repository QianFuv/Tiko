"""Runtime job and watchdog service."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.domain.reporting import Alert
from tiko.domain.runtime import (
    BackgroundJob,
    JobType,
    WatchdogCheck,
    WatchdogReport,
    WatchdogSeverity,
    WorkerHeartbeat,
    WorkerStatus,
)
from tiko.domain.simulation import SimulationRun

MAX_HEALTHY_QUEUE_DEPTH = 1000
MAX_HEALTHY_CLOCK_LAG_MS = 60_000
MAX_RUNNING_JOB_AGE_SECONDS = 3_600
MAX_STUCK_SIMULATION_SECONDS = 900
ABNORMAL_RISK_ALERT_CATEGORIES = frozenset(
    {
        "drawdown",
        "order_anomaly",
        "risk_circuit_breaker",
        "runtime_stuck",
    }
)


class RuntimeService:
    """Manage process-local runtime jobs and worker health."""

    def __init__(self) -> None:
        """Initialize the runtime service."""

        self._jobs: dict[UUID, BackgroundJob] = {}
        self._heartbeats_by_worker: dict[str, WorkerHeartbeat] = {}

    def create_job(
        self,
        job_type: JobType,
        resource_type: str,
        resource_id: str,
        payload: dict[str, object],
    ) -> BackgroundJob:
        """Create a queued runtime job record.

        Args:
            job_type: Runtime job type.
            resource_type: Resource type associated with the job.
            resource_id: Resource identifier associated with the job.
            payload: Job payload.

        Returns:
            Created queued job.
        """

        now = datetime.now(UTC)
        job = BackgroundJob(
            job_id=uuid4(),
            job_type=job_type,
            resource_type=resource_type,
            resource_id=resource_id,
            status="queued",
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.job_id] = job
        return job

    def list_jobs(self) -> list[BackgroundJob]:
        """List runtime jobs.

        Returns:
            Job records sorted by creation time.
        """

        return sorted(self._jobs.values(), key=lambda job: job.created_at)

    def count_queued_jobs(self, job_types: Sequence[JobType] | None = None) -> int:
        """Count queued runtime jobs.

        Args:
            job_types: Optional eligible job types.

        Returns:
            Number of queued jobs matching the optional type filter.
        """

        eligible_job_types = set(job_types) if job_types is not None else None
        return sum(
            1
            for job in self._jobs.values()
            if job.status == "queued"
            and (eligible_job_types is None or job.job_type in eligible_job_types)
        )

    def get_job(self, job_id: UUID) -> BackgroundJob:
        """Get one runtime job.

        Args:
            job_id: Runtime job identifier.

        Returns:
            Runtime job.

        Raises:
            KeyError: If the job does not exist.
        """

        return self._jobs[job_id]

    def claim_next_job(
        self,
        worker_name: str,
        job_types: Sequence[JobType],
    ) -> BackgroundJob | None:
        """Claim the next queued job matching worker capabilities.

        Args:
            worker_name: Worker claiming the job.
            job_types: Job types supported by the worker.

        Returns:
            Claimed running job, or `None` when no eligible queued job exists.
        """

        eligible_job_types = set(job_types)
        now = datetime.now(UTC)
        for job in self.list_jobs():
            if job.status != "queued" or job.job_type not in eligible_job_types:
                continue
            claimed_job = job.model_copy(
                update={
                    "status": "running",
                    "claimed_by": worker_name,
                    "started_at": now,
                    "updated_at": now,
                }
            )
            self._jobs[job.job_id] = claimed_job
            return claimed_job
        return None

    def complete_job(
        self,
        job_id: UUID,
        result: dict[str, object],
    ) -> BackgroundJob:
        """Mark a running job as completed.

        Args:
            job_id: Runtime job identifier.
            result: Structured job result metadata.

        Returns:
            Completed job.

        Raises:
            KeyError: If the job does not exist.
            ValueError: If the job is not running.
        """

        job = self._jobs[job_id]
        if job.status != "running":
            raise ValueError("Only running jobs can be completed.")
        now = datetime.now(UTC)
        completed_job = job.model_copy(
            update={
                "status": "completed",
                "result": result,
                "error_message": None,
                "updated_at": now,
                "completed_at": now,
            }
        )
        self._jobs[job_id] = completed_job
        return completed_job

    def fail_job(self, job_id: UUID, error_message: str) -> BackgroundJob:
        """Mark a running job as failed.

        Args:
            job_id: Runtime job identifier.
            error_message: Failure reason.

        Returns:
            Failed job.

        Raises:
            KeyError: If the job does not exist.
            ValueError: If the job is not running.
        """

        job = self._jobs[job_id]
        if job.status != "running":
            raise ValueError("Only running jobs can be failed.")
        now = datetime.now(UTC)
        failed_job = job.model_copy(
            update={
                "status": "failed",
                "error_message": error_message,
                "updated_at": now,
                "completed_at": now,
            }
        )
        self._jobs[job_id] = failed_job
        return failed_job

    def record_heartbeat(
        self,
        worker_name: str,
        worker_status: WorkerStatus,
        event_queue_depth: int,
        clock_lag_ms: int,
    ) -> WorkerHeartbeat:
        """Record the latest heartbeat for one worker.

        Args:
            worker_name: Worker process name.
            worker_status: Reported worker status.
            event_queue_depth: Current event queue depth.
            clock_lag_ms: Simulated clock lag in milliseconds.

        Returns:
            Recorded worker heartbeat.
        """

        heartbeat = WorkerHeartbeat(
            heartbeat_id=uuid4(),
            worker_name=worker_name,
            worker_status=worker_status,
            event_queue_depth=event_queue_depth,
            clock_lag_ms=clock_lag_ms,
            last_seen_at=datetime.now(UTC),
        )
        self._heartbeats_by_worker[worker_name] = heartbeat
        return heartbeat

    def list_heartbeats(self) -> list[WorkerHeartbeat]:
        """List latest worker heartbeats.

        Returns:
            Latest heartbeat per worker sorted by worker name.
        """

        return sorted(
            self._heartbeats_by_worker.values(),
            key=lambda heartbeat: heartbeat.worker_name,
        )

    def run_watchdog(
        self,
        now: datetime | None = None,
        simulation_runs: Sequence[SimulationRun] = (),
        alerts: Sequence[Alert] = (),
    ) -> WatchdogReport:
        """Run deterministic runtime watchdog checks.

        Args:
            now: Optional evaluation time for deterministic checks.
            simulation_runs: Optional simulation runs to include in checks.
            alerts: Optional run alerts to include in risk-state checks.

        Returns:
            Watchdog report over current process-local runtime state.
        """

        checked_at = now or datetime.now(UTC)
        heartbeats = self.list_heartbeats()
        queued_job_count = sum(
            1 for job in self._jobs.values() if job.status == "queued"
        )
        checks: list[WatchdogCheck] = []
        unhealthy_workers = [
            heartbeat.worker_name
            for heartbeat in heartbeats
            if heartbeat.worker_status != "healthy"
        ]
        worker_status = self._resolve_worker_status(heartbeats, unhealthy_workers)

        if not heartbeats:
            checks.append(
                WatchdogCheck(
                    code="worker_heartbeat_missing",
                    severity="warning",
                    message="No worker heartbeat has been recorded.",
                )
            )
        if unhealthy_workers:
            checks.append(
                WatchdogCheck(
                    code="worker_unhealthy",
                    severity="critical",
                    message="At least one worker reported an unhealthy status.",
                )
            )
        if queued_job_count > 0 and worker_status != "healthy":
            checks.append(
                WatchdogCheck(
                    code="queued_work_without_healthy_worker",
                    severity="warning",
                    message="Queued work exists without a healthy worker.",
                )
            )
        checks.extend(self._queue_depth_checks(heartbeats))
        checks.extend(self._clock_lag_checks(heartbeats))
        checks.extend(self._running_job_checks(checked_at))
        checks.extend(self._stuck_simulation_checks(checked_at, simulation_runs))
        checks.extend(self._abnormal_risk_state_checks(alerts))
        if not checks:
            checks.append(
                WatchdogCheck(
                    code="runtime_healthy",
                    severity="ok",
                    message="Runtime heartbeat and queue checks are healthy.",
                )
            )

        return WatchdogReport(
            report_id=uuid4(),
            checked_at=checked_at,
            worker_status=worker_status,
            queued_job_count=queued_job_count,
            unhealthy_workers=unhealthy_workers,
            checks=checks,
        )

    def _resolve_worker_status(
        self,
        heartbeats: list[WorkerHeartbeat],
        unhealthy_workers: list[str],
    ) -> WorkerStatus:
        """Resolve aggregate worker status.

        Args:
            heartbeats: Latest worker heartbeats.
            unhealthy_workers: Workers that are not healthy.

        Returns:
            Aggregate worker status.
        """

        if not heartbeats:
            return "missing"
        if unhealthy_workers:
            return "unhealthy"
        return "healthy"

    def _queue_depth_checks(
        self, heartbeats: list[WorkerHeartbeat]
    ) -> list[WatchdogCheck]:
        """Build watchdog checks for worker queue depth.

        Args:
            heartbeats: Latest worker heartbeats.

        Returns:
            Queue-depth watchdog checks.
        """

        checks: list[WatchdogCheck] = []
        for heartbeat in heartbeats:
            if heartbeat.event_queue_depth > MAX_HEALTHY_QUEUE_DEPTH:
                checks.append(
                    WatchdogCheck(
                        code="event_queue_backlog",
                        severity="warning",
                        message=(
                            f"{heartbeat.worker_name} event queue depth is "
                            f"{heartbeat.event_queue_depth}."
                        ),
                    )
                )
        return checks

    def _running_job_checks(self, now: datetime) -> list[WatchdogCheck]:
        """Build watchdog checks for stale running jobs.

        Args:
            now: Watchdog evaluation time.

        Returns:
            Running-job watchdog checks.
        """

        checks: list[WatchdogCheck] = []
        for job in self._jobs.values():
            if job.status != "running" or job.started_at is None:
                continue
            running_seconds = int((now - job.started_at).total_seconds())
            if running_seconds > MAX_RUNNING_JOB_AGE_SECONDS:
                checks.append(
                    WatchdogCheck(
                        code="running_job_stale",
                        severity="warning",
                        message=(
                            f"{job.job_type} job {job.job_id} has been running "
                            f"for {running_seconds} seconds."
                        ),
                    )
                )
        return checks

    def _stuck_simulation_checks(
        self, now: datetime, simulation_runs: Sequence[SimulationRun]
    ) -> list[WatchdogCheck]:
        """Build watchdog checks for running simulations that have not advanced.

        Args:
            now: Watchdog evaluation time.
            simulation_runs: Simulation runs to inspect.

        Returns:
            Stuck simulation watchdog checks.
        """

        checks: list[WatchdogCheck] = []
        for run in simulation_runs:
            if run.status != "running" or run.current_sim_time > run.start_sim_time:
                continue
            running_seconds = int((now - run.created_at).total_seconds())
            if running_seconds <= MAX_STUCK_SIMULATION_SECONDS:
                continue
            checks.append(
                WatchdogCheck(
                    code="simulation_stuck",
                    severity="critical",
                    message=(
                        f"Simulation {run.run_id} is running without advancing "
                        f"simulated time for {running_seconds} seconds."
                    ),
                )
            )
        return checks

    def _abnormal_risk_state_checks(
        self, alerts: Sequence[Alert]
    ) -> list[WatchdogCheck]:
        """Build watchdog checks for open abnormal risk alerts.

        Args:
            alerts: Run alerts to inspect.

        Returns:
            Risk-state watchdog checks.
        """

        checks: list[WatchdogCheck] = []
        for alert in alerts:
            if alert.status != "open" or not self._is_abnormal_risk_alert(alert):
                continue
            severity: WatchdogSeverity = (
                "critical" if alert.severity == "critical" else "warning"
            )
            checks.append(
                WatchdogCheck(
                    code="abnormal_risk_state",
                    severity=severity,
                    message=(
                        f"Open {alert.category} alert for simulation "
                        f"{alert.run_id}: {alert.message}"
                    ),
                )
            )
        return checks

    def _is_abnormal_risk_alert(self, alert: Alert) -> bool:
        """Return whether an alert represents abnormal risk state.

        Args:
            alert: Run alert to inspect.

        Returns:
            `True` when the alert should affect watchdog risk state.
        """

        return (
            alert.severity == "critical"
            or alert.category in ABNORMAL_RISK_ALERT_CATEGORIES
        )

    def _clock_lag_checks(
        self, heartbeats: list[WorkerHeartbeat]
    ) -> list[WatchdogCheck]:
        """Build watchdog checks for simulated clock lag.

        Args:
            heartbeats: Latest worker heartbeats.

        Returns:
            Clock-lag watchdog checks.
        """

        checks: list[WatchdogCheck] = []
        for heartbeat in heartbeats:
            if heartbeat.clock_lag_ms > MAX_HEALTHY_CLOCK_LAG_MS:
                checks.append(
                    WatchdogCheck(
                        code="clock_lag_high",
                        severity="warning",
                        message=(
                            f"{heartbeat.worker_name} clock lag is "
                            f"{heartbeat.clock_lag_ms} ms."
                        ),
                    )
                )
        return checks
