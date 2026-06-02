"""Risk review schemas for deterministic approval boundaries."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.account import Position
from tiko.domain.base import DomainModel
from tiko.domain.market import OrderBookSnapshot
from tiko.domain.order import SimOrder


class RiskLimits(DomainModel):
    """Represent active run-level risk limits."""

    run_id: UUID
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    minimum_data_quality_score: float = Field(ge=0.0, le=1.0)
    max_target_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    min_order_notional: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    max_order_notional: Decimal = Field(ge=Decimal("0"))
    max_leverage: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    max_drawdown: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    max_daily_loss: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    live_trading_allowed: bool = False


class RiskContext(DomainModel):
    """Represent point-in-time context for risk review."""

    positions: list[Position] = Field(default_factory=list)
    open_orders: list[SimOrder] = Field(default_factory=list)
    latest_orderbook: OrderBookSnapshot | None = None
    daily_realized_pnl: Decimal = Decimal("0")


class RiskReview(DomainModel):
    """Represent the result of independent risk review for a trade intent."""

    review_id: UUID
    decision_id: UUID
    status: Literal["approved", "rejected", "resized", "circuit_blocked"]
    original_target_weight: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    approved_target_weight: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    max_order_notional: Decimal = Field(ge=Decimal("0"))
    reasons: list[str]
    triggered_rules: list[str]
    created_at_sim_time: datetime
