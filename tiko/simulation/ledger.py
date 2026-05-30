"""Simulated ledger updates for internal fills."""

from decimal import Decimal

from tiko.domain.account import SimAccount
from tiko.domain.order import Fill


def apply_fill_to_account(account: SimAccount, fill: Fill) -> SimAccount:
    """Apply a simulated fill to account cash and equity.

    Args:
        account: Current simulated account state.
        fill: Simulated fill to apply.

    Returns:
        Updated simulated account state.
    """

    notional = fill.quantity * fill.price
    signed_cash_delta = -notional if fill.side == "buy" else notional
    cash_balance = max(
        Decimal("0"), account.cash_balance + signed_cash_delta - fill.fee
    )
    total_equity = max(Decimal("0"), account.total_equity - fill.fee)
    return account.model_copy(
        update={
            "cash_balance": cash_balance,
            "total_equity": total_equity,
            "realized_pnl": account.realized_pnl - fill.fee,
        }
    )
