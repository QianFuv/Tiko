"""Portfolio planning schemas for simulated order sizing."""

from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from tiko.domain.base import DomainModel
from tiko.domain.order import OrderRequest

PortfolioOrderPlanStatus = Literal["order_created", "no_order"]


class PortfolioOrderPlan(DomainModel):
    """Represent a portfolio sizing decision before broker submission."""

    run_id: UUID
    account_id: UUID
    decision_id: UUID | None = None
    symbol: str = Field(min_length=1)
    status: PortfolioOrderPlanStatus
    reason: str | None = Field(default=None, min_length=1)
    sizing_explanation: str = Field(min_length=1)
    target_notional: Decimal
    current_notional: Decimal
    delta_notional: Decimal
    approved_delta_notional: Decimal
    reference_price: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(ge=Decimal("0"))
    expected_notional: Decimal = Field(ge=Decimal("0"))
    estimated_fee: Decimal = Field(ge=Decimal("0"))
    estimated_slippage_bps: Decimal = Field(ge=Decimal("0"))
    order_request: OrderRequest | None = None

    @model_validator(mode="after")
    def validate_order_request_status(self) -> Self:
        """Validate consistency between plan status and order request.

        Returns:
            Validated portfolio order plan.

        Raises:
            ValueError: If status and order request presence disagree.
        """

        if self.status == "order_created" and self.order_request is None:
            raise ValueError("order_created plans require order_request.")
        if self.status == "no_order" and self.order_request is not None:
            raise ValueError("no_order plans must not include order_request.")
        return self
