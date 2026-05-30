"""Account and position schemas for simulated ledger state."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel


class SimAccount(DomainModel):
    """Represent a simulated account that never maps to a real exchange balance."""

    account_id: UUID
    name: str = Field(min_length=1)
    base_currency: str = "USDT"
    initial_equity: Decimal = Field(gt=Decimal("0"))
    cash_balance: Decimal = Field(ge=Decimal("0"))
    total_equity: Decimal = Field(ge=Decimal("0"))
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_drawdown: Decimal
    status: Literal["active", "paused", "liquidated", "stopped"]


class Position(DomainModel):
    """Represent a simulated position produced by internal fills only."""

    position_id: UUID
    account_id: UUID
    symbol: str = Field(min_length=1)
    side: Literal["long", "short", "flat"]
    quantity: Decimal = Field(ge=Decimal("0"))
    avg_entry_price: Decimal = Field(ge=Decimal("0"))
    mark_price: Decimal = Field(ge=Decimal("0"))
    notional: Decimal = Field(ge=Decimal("0"))
    leverage: Decimal = Field(ge=Decimal("0"))
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    liquidation_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    updated_at_sim_time: datetime
