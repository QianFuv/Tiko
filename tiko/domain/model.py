"""Model registry schemas for research artifacts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

ModelType = Literal["rl", "ml", "rule"]
ModelStatus = Literal["draft", "validated", "paper_enabled", "archived"]


class ModelRegistryEntry(DomainModel):
    """Represent a research model version eligible for simulated use."""

    model_id: UUID
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    model_type: ModelType
    algorithm: str = Field(min_length=1)
    training_dataset_id: UUID
    validation_dataset_id: UUID
    metrics: dict[str, object]
    artifact_uri: str = Field(min_length=1)
    status: ModelStatus
    created_at: datetime
