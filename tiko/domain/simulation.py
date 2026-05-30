"""Simulation run schemas for lifecycle and metrics state."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.account import SimAccount
from tiko.domain.base import DomainModel


class SimulationRun(DomainModel):
    """Represent a simulation run and its current clock state."""

    run_id: UUID
    name: str = Field(min_length=1)
    status: Literal["created", "running", "paused", "stopped", "completed"]
    mode: Literal["historical_replay", "live_simulated_clock", "synthetic_market"]
    account: SimAccount
    symbols: list[str]
    start_sim_time: datetime
    current_sim_time: datetime
    end_sim_time: datetime | None = None
    speed_multiplier: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    config: dict[str, object]
    created_at: datetime
