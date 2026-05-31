"""Experiment schemas for simulated research workflows."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

ExperimentKind = Literal[
    "backtest", "walk_forward", "parameter_sweep", "model_evaluation"
]
ExperimentStatus = Literal["draft", "queued", "running", "completed", "failed"]


class ExperimentRecord(DomainModel):
    """Represent a research experiment tracked by the control plane."""

    experiment_id: UUID
    name: str = Field(min_length=1)
    kind: ExperimentKind
    hypothesis: str = Field(min_length=1)
    dataset_id: UUID
    model_id: UUID | None = None
    parameters: dict[str, object] = Field(default_factory=dict)
    status: ExperimentStatus
    metrics: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    queued_at: datetime | None = None
    completed_at: datetime | None = None
