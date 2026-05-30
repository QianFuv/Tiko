"""Order and fill schemas for the internal simulated exchange."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel


class OrderRequest(DomainModel):
    """Represent a portfolio-generated request for a simulated order."""

    run_id: UUID
    account_id: UUID
    decision_id: UUID | None = None
    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: Decimal = Field(gt=Decimal("0"))
    limit_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    submitted_at_sim_time: datetime


class SimOrder(DomainModel):
    """Represent an order lifecycle record inside the simulated broker."""

    order_id: UUID
    run_id: UUID
    account_id: UUID
    decision_id: UUID | None = None
    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: Decimal = Field(gt=Decimal("0"))
    limit_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    status: Literal[
        "created",
        "submitted",
        "accepted",
        "rejected",
        "open",
        "partially_filled",
        "filled",
        "canceled",
        "expired",
    ]
    submitted_at_sim_time: datetime
    updated_at_sim_time: datetime


class Fill(DomainModel):
    """Represent a simulated fill produced by the matching engine."""

    fill_id: UUID
    order_id: UUID
    run_id: UUID
    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))
    fee: Decimal = Field(ge=Decimal("0"))
    slippage_bps: Decimal = Field(ge=Decimal("0"))
    filled_at_sim_time: datetime
