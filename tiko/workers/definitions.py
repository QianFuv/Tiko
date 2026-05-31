"""Shared worker process definitions."""

from dataclasses import dataclass
from uuid import UUID

from tiko.domain.runtime import JobType


@dataclass(frozen=True)
class WorkerDefinition:
    """Describe one runtime worker process role."""

    worker_name: str
    job_types: tuple[JobType, ...]
    description: str


@dataclass(frozen=True)
class WorkerExecutionResult:
    """Summarize one deterministic worker execution pass."""

    worker_name: str
    claimed_job_ids: tuple[UUID, ...]
    completed_job_ids: tuple[UUID, ...]
    failed_job_ids: tuple[UUID, ...]
    remaining_queue_depth: int
