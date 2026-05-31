"""Observation schemas for point-in-time agent inputs."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from tiko.domain.account import Position, SimAccount
from tiko.domain.base import DomainModel
from tiko.domain.market import Candle, MarketEvent, OrderBookSnapshot
from tiko.domain.memory import MemoryEntry
from tiko.domain.risk import RiskLimits


class Observation(DomainModel):
    """Represent point-in-time-safe inputs for agent evaluation."""

    observation_id: UUID
    run_id: UUID
    symbol: str = Field(min_length=1)
    as_of: datetime
    account: SimAccount
    candles: list[Candle]
    events: list[MarketEvent]
    orderbook: OrderBookSnapshot | None = None
    features: dict[str, object] = Field(default_factory=dict)
    positions: list[Position] = Field(default_factory=list)
    risk_limits: RiskLimits | None = None
    memory: list[MemoryEntry] = Field(default_factory=list)
