"""Decision schemas for structured agent trading intent."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel


class TradeIntent(DomainModel):
    """Represent the only executable-adjacent output allowed from agents."""

    decision_id: UUID
    run_id: UUID
    agent_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    market_type: Literal["spot", "perp", "synthetic"]
    action: Literal[
        "open_long",
        "open_short",
        "increase_long",
        "increase_short",
        "reduce_long",
        "reduce_short",
        "close_position",
        "hold",
        "rebalance",
    ]
    target_weight: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    target_notional: Decimal | None = Field(default=None, ge=Decimal("0"))
    max_leverage: Decimal = Field(ge=Decimal("0"))
    confidence: float = Field(ge=0.0, le=1.0)
    expected_holding_period: str = Field(min_length=1)
    thesis: str = Field(min_length=1)
    evidence: list[dict[str, object]]
    invalidation_conditions: list[str]
    data_quality_score: float = Field(ge=0.0, le=1.0)
    created_at_sim_time: datetime
