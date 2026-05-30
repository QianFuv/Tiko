"""Observation schemas for point-in-time agent inputs."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from tiko.domain.account import SimAccount
from tiko.domain.base import DomainModel
from tiko.domain.market import Candle, MarketEvent


class Observation(DomainModel):
    """Represent point-in-time-safe inputs for agent evaluation."""

    observation_id: UUID
    run_id: UUID
    symbol: str = Field(min_length=1)
    as_of: datetime
    account: SimAccount
    candles: list[Candle]
    events: list[MarketEvent]
