"""Decision schemas for structured agent trading intent."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

DecisionStatus = Literal[
    "created",
    "schema_validated",
    "risk_reviewed",
    "approved",
    "rejected",
    "resized",
    "circuit_blocked",
    "converted_to_order",
    "no_order",
    "reviewed",
]


class TradeIntent(DomainModel):
    """Represent the only executable-adjacent output allowed from agents."""

    decision_id: UUID
    run_id: UUID
    observation_id: UUID | None = None
    agent_run_id: UUID | None = None
    input_data_as_of: datetime | None = None
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
    status: DecisionStatus = "created"
    created_at_sim_time: datetime


class DecisionReview(DomainModel):
    """Represent posterior review metrics for one structured trade intent."""

    review_id: UUID
    decision_id: UUID
    run_id: UUID
    horizon: str = Field(min_length=1)
    realized_return: Decimal
    max_adverse_excursion: Decimal
    max_favorable_excursion: Decimal
    was_correct_directionally: bool
    error_tags: list[str]
    reviewer_summary: str = Field(min_length=1)
    created_at_sim_time: datetime
