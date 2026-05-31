"""Memory schemas for auxiliary simulation review context."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

MemoryType = Literal["decision", "failure", "regime", "agent", "experiment"]


class MemoryEntry(DomainModel):
    """Represent auxiliary memory that cannot bypass validation or risk."""

    memory_id: UUID
    run_id: UUID
    decision_id: UUID | None = None
    memory_type: MemoryType
    summary: str = Field(min_length=1)
    content: dict[str, object]
    tags: list[str]
    available_at_sim_time: datetime
    created_at: datetime


class MemorySearchResult(DomainModel):
    """Represent one scored memory retrieval result."""

    entry: MemoryEntry
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)
