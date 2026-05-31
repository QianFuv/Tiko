"""Account and position schemas for simulated ledger state."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

LedgerEntryType = Literal["fill", "fee", "funding", "mark_to_market", "adjustment"]


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


class LedgerEntry(DomainModel):
    """Represent one simulated ledger entry produced by internal execution."""

    ledger_entry_id: UUID
    run_id: UUID
    account_id: UUID
    fill_id: UUID | None = None
    entry_type: LedgerEntryType
    symbol: str | None = None
    quantity: Decimal = Field(ge=Decimal("0"))
    price: Decimal | None = Field(default=None, ge=Decimal("0"))
    notional: Decimal
    cash_delta: Decimal
    fee: Decimal
    realized_pnl_delta: Decimal
    created_at_sim_time: datetime
    created_at: datetime


class PortfolioSnapshot(DomainModel):
    """Represent point-in-time simulated portfolio state."""

    snapshot_id: UUID
    run_id: UUID
    account_id: UUID
    simulated_time: datetime
    cash_balance: Decimal
    total_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_drawdown: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    created_at: datetime


class MetricSnapshot(DomainModel):
    """Represent point-in-time simulated performance metrics."""

    snapshot_id: UUID
    run_id: UUID
    simulated_time: datetime
    metrics: dict[str, object]
    created_at: datetime
