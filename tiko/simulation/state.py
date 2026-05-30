"""Mutable in-memory state containers for simulation services."""

from dataclasses import dataclass, field

from tiko.domain.decision import TradeIntent
from tiko.domain.market import Candle, MarketEvent
from tiko.domain.order import Fill, SimOrder
from tiko.domain.risk import RiskReview
from tiko.domain.simulation import SimulationRun
from tiko.simulation.replay import MarketReplay


@dataclass
class SimulationState:
    """Hold mutable process-local state for one simulation run."""

    run: SimulationRun
    step_index: int = 0
    market_replay: MarketReplay | None = None
    candles: list[Candle] = field(default_factory=list)
    events: list[MarketEvent] = field(default_factory=list)
    decisions: list[TradeIntent] = field(default_factory=list)
    risk_reviews: list[RiskReview] = field(default_factory=list)
    orders: list[SimOrder] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)


@dataclass(frozen=True)
class SimulationStepResult:
    """Return observable artifacts produced by one simulation step."""

    run: SimulationRun
    candle: Candle
    event: MarketEvent
    decision: TradeIntent
    risk_review: RiskReview
    order: SimOrder | None
    fill: Fill | None
