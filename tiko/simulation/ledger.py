"""Simulated ledger updates for internal fills."""

from dataclasses import dataclass
from decimal import Decimal

from tiko.domain.account import SimAccount
from tiko.domain.order import Fill


@dataclass(frozen=True)
class LedgerUpdate:
    """Describe the account impact of one simulated fill."""

    account: SimAccount
    notional: Decimal
    cash_delta: Decimal
    fee: Decimal


def apply_fill_to_ledger(account: SimAccount, fill: Fill) -> LedgerUpdate:
    """Apply a simulated fill and return structured ledger metadata.

    Args:
        account: Current simulated account state.
        fill: Simulated fill to apply.

    Returns:
        Ledger update with updated account and cash impact details.
    """

    notional = fill.quantity * fill.price
    signed_cash_delta = -notional if fill.side == "buy" else notional
    cash_delta = signed_cash_delta - fill.fee
    cash_balance = max(Decimal("0"), account.cash_balance + cash_delta)
    total_equity = max(Decimal("0"), account.total_equity - fill.fee)
    updated_account = account.model_copy(
        update={
            "cash_balance": cash_balance,
            "total_equity": total_equity,
            "realized_pnl": account.realized_pnl - fill.fee,
        }
    )
    return LedgerUpdate(
        account=updated_account,
        notional=notional,
        cash_delta=cash_delta,
        fee=fill.fee,
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
