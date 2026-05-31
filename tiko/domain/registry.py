"""Control-plane registry schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel
from tiko.domain.security import Role

SimulationDefinitionMode = Literal[
    "historical_replay", "live_simulated_clock", "synthetic_market"
]


class UserProfile(DomainModel):
    """Represent a persisted control-plane user profile."""

    user_id: str = Field(min_length=1)
    role: Role
    display_name: str = Field(min_length=1)
    is_disabled: bool = False
    created_at: datetime


class ProjectRecord(DomainModel):
    """Represent a persisted project namespace."""

    project_id: UUID
    name: str = Field(min_length=1)
    owner_user_id: str = Field(min_length=1)
    description: str = ""
    created_at: datetime


class SimulationDefinition(DomainModel):
    """Represent reusable simulation configuration metadata."""

    simulation_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1)
    mode: SimulationDefinitionMode
    symbols: list[str] = Field(default_factory=list)
    config: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
