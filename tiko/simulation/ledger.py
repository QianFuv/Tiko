"""Simulated ledger updates for internal fills."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from tiko.domain.account import Position, SimAccount
from tiko.domain.order import Fill


@dataclass(frozen=True)
class LedgerUpdate:
    """Describe the account impact of one simulated fill."""

    account: SimAccount
    notional: Decimal
    cash_delta: Decimal
    fee: Decimal
    realized_pnl_delta: Decimal


@dataclass(frozen=True)
class FundingUpdate:
    """Describe the account impact of simulated funding."""

    account: SimAccount
    notional: Decimal
    cash_delta: Decimal
    funding_payment: Decimal


@dataclass(frozen=True)
class AccountedPosition:
    """Represent one open position produced by replaying simulated fills."""

    symbol: str
    side: Literal["long", "short"]
    quantity: Decimal
    avg_entry_price: Decimal
    realized_pnl: Decimal
    latest_time: datetime


@dataclass(frozen=True)
class FillAccountingResult:
    """Represent realized PnL and open positions derived from fills."""

    positions: tuple[AccountedPosition, ...]
    realized_pnl: Decimal


@dataclass
class PositionAccumulator:
    """Track weighted-average position state for one symbol."""

    quantity: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    latest_time: datetime | None = None


def calculate_fill_accounting(fills: Sequence[Fill]) -> FillAccountingResult:
    """Replay fills into weighted-average open positions and realized PnL.

    Args:
        fills: Simulated fills to account for.

    Returns:
        Fill accounting result with open positions and realized trade PnL.
    """

    accumulators: dict[str, PositionAccumulator] = {}
    indexed_fills = enumerate(fills)
    for _index, fill in sorted(
        indexed_fills,
        key=lambda indexed_fill: (
            indexed_fill[1].filled_at_sim_time,
            indexed_fill[0],
        ),
    ):
        accumulator = accumulators.setdefault(fill.symbol, PositionAccumulator())
        signed_quantity = fill.quantity if fill.side == "buy" else -fill.quantity
        accumulator.latest_time = fill.filled_at_sim_time
        if accumulator.quantity == Decimal("0"):
            accumulator.quantity = signed_quantity
            accumulator.avg_entry_price = fill.price
            continue
        if (accumulator.quantity > Decimal("0")) == (signed_quantity > Decimal("0")):
            total_quantity = abs(accumulator.quantity) + abs(signed_quantity)
            total_cost = (
                abs(accumulator.quantity) * accumulator.avg_entry_price
                + abs(signed_quantity) * fill.price
            )
            accumulator.quantity += signed_quantity
            accumulator.avg_entry_price = total_cost / total_quantity
            continue
        closing_quantity = min(abs(accumulator.quantity), abs(signed_quantity))
        if accumulator.quantity > Decimal("0"):
            accumulator.realized_pnl += (
                fill.price - accumulator.avg_entry_price
            ) * closing_quantity
        else:
            accumulator.realized_pnl += (
                accumulator.avg_entry_price - fill.price
            ) * closing_quantity
        remaining_quantity = accumulator.quantity + signed_quantity
        if remaining_quantity == Decimal("0"):
            accumulator.quantity = Decimal("0")
            accumulator.avg_entry_price = Decimal("0")
        elif (remaining_quantity > Decimal("0")) == (
            accumulator.quantity > Decimal("0")
        ):
            accumulator.quantity = remaining_quantity
        else:
            accumulator.quantity = remaining_quantity
            accumulator.avg_entry_price = fill.price

    positions = tuple(
        AccountedPosition(
            symbol=symbol,
            side="long" if accumulator.quantity > Decimal("0") else "short",
            quantity=abs(accumulator.quantity),
            avg_entry_price=accumulator.avg_entry_price,
            realized_pnl=accumulator.realized_pnl,
            latest_time=(
                accumulator.latest_time
                if accumulator.latest_time is not None
                else fills[0].filled_at_sim_time
            ),
        )
        for symbol, accumulator in sorted(accumulators.items())
        if accumulator.quantity != Decimal("0")
    )
    realized_pnl = sum(
        (accumulator.realized_pnl for accumulator in accumulators.values()),
        Decimal("0"),
    )
    return FillAccountingResult(positions=positions, realized_pnl=realized_pnl)


def apply_fill_to_ledger(
    account: SimAccount,
    fill: Fill,
    prior_fills: Sequence[Fill] = (),
) -> LedgerUpdate:
    """Apply a simulated fill and return structured ledger metadata.

    Args:
        account: Current simulated account state.
        fill: Simulated fill to apply.
        prior_fills: Earlier fills for calculating closed trade PnL.

    Returns:
        Ledger update with updated account and cash impact details.
    """

    notional = fill.quantity * fill.price
    signed_cash_delta = -notional if fill.side == "buy" else notional
    cash_delta = signed_cash_delta - fill.fee
    cash_balance = max(Decimal("0"), account.cash_balance + cash_delta)
    previous_accounting = calculate_fill_accounting(prior_fills)
    current_accounting = calculate_fill_accounting((*prior_fills, fill))
    realized_trade_pnl_delta = (
        current_accounting.realized_pnl - previous_accounting.realized_pnl
    )
    realized_pnl_delta = realized_trade_pnl_delta - fill.fee
    total_equity = max(Decimal("0"), account.total_equity + realized_pnl_delta)
    updated_account = account.model_copy(
        update={
            "cash_balance": cash_balance,
            "total_equity": total_equity,
            "realized_pnl": account.realized_pnl + realized_pnl_delta,
        }
    )
    return LedgerUpdate(
        account=updated_account,
        notional=notional,
        cash_delta=cash_delta,
        fee=fill.fee,
        realized_pnl_delta=realized_pnl_delta,
    )


def apply_funding_to_ledger(
    account: SimAccount,
    positions: list[Position] | tuple[Position, ...],
    funding_rate: Decimal,
) -> FundingUpdate:
    """Apply simulated funding to account cash and realized PnL.

    Args:
        account: Current simulated account state.
        positions: Current marked positions.
        funding_rate: Fixed funding rate for the interval.

    Returns:
        Funding update with updated account and cash impact details.
    """

    signed_notional = sum(
        (
            position.notional if position.side == "long" else -position.notional
            for position in positions
        ),
        Decimal("0"),
    )
    funding_payment = signed_notional * funding_rate
    cash_delta = -funding_payment
    updated_account = account.model_copy(
        update={
            "cash_balance": max(Decimal("0"), account.cash_balance + cash_delta),
            "realized_pnl": account.realized_pnl + cash_delta,
            "total_equity": max(Decimal("0"), account.total_equity + cash_delta),
        }
    )
    return FundingUpdate(
        account=updated_account,
        notional=abs(signed_notional),
        cash_delta=cash_delta,
        funding_payment=funding_payment,
    )


def apply_fill_to_account(account: SimAccount, fill: Fill) -> SimAccount:
    """Apply a simulated fill to account cash and equity.

    Args:
        account: Current simulated account state.
        fill: Simulated fill to apply.

    Returns:
        Updated simulated account state.
    """

    return apply_fill_to_ledger(account, fill).account
