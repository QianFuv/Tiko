"""Runtime job, worker heartbeat, and watchdog schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

JobType = Literal[
    "agent_inference",
    "backtest",
    "experiment_run",
    "report_generation",
    "rl_training",
]
JobStatus = Literal["queued", "running", "completed", "failed"]
WorkerStatus = Literal["healthy", "unhealthy", "missing"]
WatchdogSeverity = Literal["ok", "warning", "critical"]


class BackgroundJob(DomainModel):
    """Represent a queued runtime job."""

    job_id: UUID
    job_type: JobType
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    status: JobStatus
    payload: dict[str, object] = Field(default_factory=dict)
    result: dict[str, object] = Field(default_factory=dict)
    claimed_by: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkerHeartbeat(DomainModel):
    """Represent the latest heartbeat from a runtime process."""

    heartbeat_id: UUID
    worker_name: str = Field(min_length=1)
    worker_status: WorkerStatus
    event_queue_depth: int = Field(ge=0)
    clock_lag_ms: int = Field(ge=0)
    last_seen_at: datetime


class WatchdogCheck(DomainModel):
    """Represent one watchdog check result."""

    code: str = Field(min_length=1)
    severity: WatchdogSeverity
    message: str = Field(min_length=1)


class WatchdogReport(DomainModel):
    """Summarize runtime health checks."""

    report_id: UUID
    checked_at: datetime
    worker_status: WorkerStatus
    queued_job_count: int = Field(ge=0)
    unhealthy_workers: list[str] = Field(default_factory=list)
    checks: list[WatchdogCheck] = Field(default_factory=list)
