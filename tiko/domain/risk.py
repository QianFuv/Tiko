"""Risk review schemas for deterministic approval boundaries."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel


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
