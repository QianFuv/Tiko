"""Mutable in-memory state containers for simulation services."""

from dataclasses import dataclass, field

from tiko.domain.account import LedgerEntry, MetricSnapshot, PortfolioSnapshot, Position
from tiko.domain.decision import DecisionReview, TradeIntent
from tiko.domain.market import Candle, MarketEvent
from tiko.domain.memory import MemoryEntry
from tiko.domain.order import Fill, SimOrder
from tiko.domain.reporting import Alert, ReportArtifact
from tiko.domain.risk import RiskLimits, RiskReview
from tiko.domain.simulation import SimulationRun
from tiko.simulation.replay import MarketReplay


@dataclass
class SimulationState:
    """Hold mutable process-local state for one simulation run."""

    run: SimulationRun
    risk_limits: RiskLimits
    step_index: int = 0
    market_replay: MarketReplay | None = None
    candles: list[Candle] = field(default_factory=list)
    events: list[MarketEvent] = field(default_factory=list)
    decisions: list[TradeIntent] = field(default_factory=list)
    decision_reviews: list[DecisionReview] = field(default_factory=list)
    memory_entries: list[MemoryEntry] = field(default_factory=list)
    reports: list[ReportArtifact] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    risk_reviews: list[RiskReview] = field(default_factory=list)
    orders: list[SimOrder] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    ledger_entries: list[LedgerEntry] = field(default_factory=list)
    portfolio_snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    metric_snapshots: list[MetricSnapshot] = field(default_factory=list)


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
    positions: tuple[Position, ...]
    ledger_entry: LedgerEntry | None
    portfolio_snapshot: PortfolioSnapshot
    metric_snapshot: MetricSnapshot
