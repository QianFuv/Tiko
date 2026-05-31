"""Shared worker process definitions."""

from dataclasses import dataclass

from tiko.domain.runtime import JobType


@dataclass(frozen=True)
class WorkerDefinition:
    """Describe one runtime worker process role."""

    worker_name: str
    job_types: tuple[JobType, ...]
    description: str
