"""Runtime job and watchdog service."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.domain.runtime import (
    BackgroundJob,
    JobType,
    WatchdogCheck,
    WatchdogReport,
    WorkerHeartbeat,
    WorkerStatus,
)

MAX_HEALTHY_QUEUE_DEPTH = 1000
MAX_HEALTHY_CLOCK_LAG_MS = 60_000


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

    def run_watchdog(self) -> WatchdogReport:
        """Run deterministic runtime watchdog checks.

        Returns:
            Watchdog report over current process-local runtime state.
        """

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
            checked_at=datetime.now(UTC),
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
