"""Shared Pydantic configuration for Tiko domain schemas."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Provide immutable, closed domain models for simulation contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")
