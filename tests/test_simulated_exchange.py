"""Tests for simulated exchange execution components."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import pytest

from tiko.domain.account import Position, SimAccount
from tiko.domain.order import Fill, OrderRequest
from tiko.domain.simulation import SimulationRun
from tiko.simulation.broker import SimBroker
from tiko.simulation.fee import FeeEngine
from tiko.simulation.ledger import (
    apply_fill_to_account,
    apply_fill_to_ledger,
    apply_funding_to_ledger,
    calculate_fill_accounting,
)
from tiko.simulation.matching import MatchingEngine
from tiko.simulation.metrics import MetricsEngine
from tiko.simulation.slippage import SlippageEngine


def create_order_request(side: Literal["buy", "sell"] = "buy") -> OrderRequest:
    """Create a market order request for simulated exchange tests.

    Args:
        side: Order side.

    Returns:
        Order request domain model.
    """

    return OrderRequest(
        run_id=uuid4(),
        account_id=uuid4(),
        decision_id=uuid4(),
        symbol="BTCUSDT",
        side=side,
        order_type="market",
        quantity=Decimal("2"),
        submitted_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_limit_order_request(
    side: Literal["buy", "sell"],
    limit_price: Decimal | None,
) -> OrderRequest:
    """Create a limit order request for simulated exchange tests.

    Args:
        side: Order side.
        limit_price: Optional limit price.

    Returns:
        Limit order request domain model.
    """

    return OrderRequest(
        run_id=uuid4(),
        account_id=uuid4(),
        decision_id=uuid4(),
        symbol="BTCUSDT",
        side=side,
        order_type="limit",
        quantity=Decimal("2"),
        limit_price=limit_price,
        submitted_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_fill(
    side: Literal["buy", "sell"],
    quantity: Decimal,
    price: Decimal,
    hour: int,
    fee: Decimal = Decimal("0"),
) -> Fill:
    """Create a deterministic fill for accounting tests.

    Args:
        side: Fill side.
        quantity: Fill quantity.
        price: Fill price.
        hour: Simulated fill hour.
        fee: Fill fee.

    Returns:
        Fill domain model.
    """

    return Fill(
        fill_id=uuid4(),
        order_id=uuid4(),
        run_id=uuid4(),
        symbol="BTCUSDT",
        side=side,
        quantity=quantity,
        price=price,
        fee=fee,
        slippage_bps=Decimal("0"),
        filled_at_sim_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
    )


def create_account() -> SimAccount:
    """Create a simulated account for ledger tests.

    Returns:
        Simulated account domain model.
    """

    return SimAccount(
        account_id=uuid4(),
        name="metrics-account",
        initial_equity=Decimal("1000"),
        cash_balance=Decimal("1000"),
        total_equity=Decimal("1000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
    )


def create_run(account: SimAccount) -> SimulationRun:
    """Create a simulation run for metrics tests.

    Args:
        account: Simulated account.

    Returns:
        Simulation run domain model.
    """

    return SimulationRun(
        run_id=uuid4(),
        name="metrics-run",
        status="running",
        mode="synthetic_market",
        account=account,
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        current_sim_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
        config={"data_source": "synthetic"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_position(side: Literal["long", "short"]) -> Position:
    """Create a marked position for funding tests.

    Args:
        side: Position side.

    Returns:
        Simulated position.
    """

    return Position(
        position_id=uuid4(),
        account_id=uuid4(),
        symbol="BTCUSDT",
        side=side,
        quantity=Decimal("2"),
        avg_entry_price=Decimal("100"),
        mark_price=Decimal("100"),
        notional=Decimal("200"),
        leverage=Decimal("1"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        liquidation_price=None,
        updated_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_fee_engine_calculates_basis_point_fee() -> None:
    """Verify fee calculation uses notional and basis points."""

    fee = FeeEngine(fee_bps=Decimal("5")).calculate_fee(
        quantity=Decimal("2"),
        price=Decimal("100.02"),
    )

    assert fee == Decimal("0.10002")


def test_slippage_engine_adjusts_buy_and_sell_prices() -> None:
    """Verify slippage moves buy and sell prices in opposite directions."""

    engine = SlippageEngine(slippage_bps=Decimal("2"))

    assert engine.apply_market_slippage(Decimal("100"), "buy") == Decimal("100.02")
    assert engine.apply_market_slippage(Decimal("100"), "sell") == Decimal("99.98")


def test_matching_engine_creates_filled_order_and_fill() -> None:
    """Verify market matching creates linked order and fill records."""

    order, fill = MatchingEngine().match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
    )

    assert order.status == "filled"
    assert order.order_id == fill.order_id
    assert fill.price == Decimal("100.02")
    assert fill.fee == Decimal("0.10002")
    assert fill.slippage_bps == Decimal("2")


def test_matching_engine_fills_crossed_limit_order_with_maker_fee() -> None:
    """Verify crossed limit orders fill at reference price with maker fees."""

    order, fill = MatchingEngine(
        maker_fee_engine=FeeEngine(fee_bps=Decimal("2")),
    ).match_limit_order(
        create_limit_order_request("buy", Decimal("101")),
        reference_price=Decimal("100"),
    )

    assert fill is not None
    assert order.status == "filled"
    assert order.order_id == fill.order_id
    assert fill.price == Decimal("100")
    assert fill.fee == Decimal("0.04")
    assert fill.slippage_bps == Decimal("0")


def test_matching_engine_leaves_uncrossed_limit_order_open() -> None:
    """Verify uncrossed limit orders remain open without fills."""

    order, fill = MatchingEngine().match_limit_order(
        create_limit_order_request("buy", Decimal("99")),
        reference_price=Decimal("100"),
    )

    assert order.status == "open"
    assert order.limit_price == Decimal("99")
    assert fill is None


def test_matching_engine_requires_limit_price() -> None:
    """Verify limit matching rejects incomplete limit requests."""

    with pytest.raises(ValueError, match="limit_price"):
        MatchingEngine().match_limit_order(
            create_limit_order_request("sell", None),
            reference_price=Decimal("100"),
        )


def test_sim_broker_preserves_immediate_fill_defaults() -> None:
    """Verify broker output remains compatible with previous behavior."""

    order, fill = SimBroker().submit_market_order(
        create_order_request("sell"),
        reference_price=Decimal("100"),
    )

    assert order.status == "filled"
    assert fill.price == Decimal("99.98")
    assert fill.fee == Decimal("0.09998")
    assert fill.order_id == order.order_id


def test_sim_broker_uses_maker_fee_for_limit_orders() -> None:
    """Verify broker limit submissions use configured maker fees."""

    order, fill = SimBroker(
        fee_bps=Decimal("5"),
        maker_fee_bps=Decimal("2"),
    ).submit_limit_order(
        create_limit_order_request("sell", Decimal("99")),
        reference_price=Decimal("100"),
    )

    assert fill is not None
    assert order.status == "filled"
    assert fill.price == Decimal("100")
    assert fill.fee == Decimal("0.04")
    assert fill.slippage_bps == Decimal("0")


def test_ledger_update_preserves_account_output_and_exposes_metadata() -> None:
    """Verify ledger metadata matches the account update path."""

    account = create_account()
    _order, fill = MatchingEngine().match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
    )

    ledger_update = apply_fill_to_ledger(account, fill)

    assert apply_fill_to_account(account, fill) == ledger_update.account
    assert ledger_update.notional == Decimal("200.04")
    assert ledger_update.fee == Decimal("0.10002")
    assert ledger_update.cash_delta == Decimal("-200.14002")
    assert ledger_update.realized_pnl_delta == Decimal("-0.10002")
    assert ledger_update.account.realized_pnl == Decimal("-0.10002")


def test_fill_accounting_partial_close_preserves_average_entry() -> None:
    """Verify partial reductions realize PnL without moving remaining cost basis."""

    accounting = calculate_fill_accounting(
        [
            create_fill("buy", Decimal("2"), Decimal("100"), 1),
            create_fill("sell", Decimal("0.5"), Decimal("110"), 2),
        ]
    )

    position = accounting.positions[0]
    assert accounting.realized_pnl == Decimal("5.0")
    assert position.side == "long"
    assert position.quantity == Decimal("1.5")
    assert position.avg_entry_price == Decimal("100")
    assert position.realized_pnl == Decimal("5.0")


def test_fill_accounting_full_close_realizes_trade_pnl() -> None:
    """Verify full closes leave no open position and realize trade PnL."""

    open_fill = create_fill(
        "buy",
        Decimal("2"),
        Decimal("100"),
        1,
        fee=Decimal("0.10"),
    )
    close_fill = create_fill(
        "sell",
        Decimal("2"),
        Decimal("90"),
        2,
        fee=Decimal("0.09"),
    )
    open_update = apply_fill_to_ledger(create_account(), open_fill)
    close_update = apply_fill_to_ledger(
        open_update.account,
        close_fill,
        prior_fills=[open_fill],
    )
    accounting = calculate_fill_accounting([open_fill, close_fill])

    assert accounting.positions == ()
    assert accounting.realized_pnl == Decimal("-20")
    assert close_update.realized_pnl_delta == Decimal("-20.09")
    assert close_update.account.realized_pnl == Decimal("-20.19")


def test_fill_accounting_reversal_opens_residual_at_reversal_price() -> None:
    """Verify reversals realize the closed side and open residual exposure."""

    accounting = calculate_fill_accounting(
        [
            create_fill("buy", Decimal("1"), Decimal("100"), 1),
            create_fill("sell", Decimal("2"), Decimal("110"), 2),
        ]
    )

    position = accounting.positions[0]
    assert accounting.realized_pnl == Decimal("10")
    assert position.side == "short"
    assert position.quantity == Decimal("1")
    assert position.avg_entry_price == Decimal("110")
    assert position.realized_pnl == Decimal("10")


def test_funding_update_charges_longs_and_pays_shorts() -> None:
    """Verify simulated funding applies signed notional cash deltas."""

    account = create_account()
    long_update = apply_funding_to_ledger(
        account,
        [create_position("long")],
        Decimal("0.001"),
    )
    short_update = apply_funding_to_ledger(
        account,
        [create_position("short")],
        Decimal("0.001"),
    )
    zero_update = apply_funding_to_ledger(
        account,
        [create_position("long")],
        Decimal("0"),
    )

    assert long_update.notional == Decimal("200")
    assert long_update.funding_payment == Decimal("0.200")
    assert long_update.cash_delta == Decimal("-0.200")
    assert long_update.account.realized_pnl == Decimal("-0.200")
    assert short_update.funding_payment == Decimal("-0.200")
    assert short_update.cash_delta == Decimal("0.200")
    assert short_update.account.realized_pnl == Decimal("0.200")
    assert zero_update.cash_delta == Decimal("0")


def test_metrics_engine_summarizes_simulated_execution() -> None:
    """Verify metrics summarize simulated orders, fills, fees, and return."""

    account = create_account()
    order, fill = MatchingEngine().match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
    )
    updated_account = apply_fill_to_account(account, fill)
    run = create_run(updated_account)

    metrics = MetricsEngine().summarize_execution(run, [order], [fill])

    assert metrics.run_id == run.run_id
    assert metrics.order_count == 1
    assert metrics.fill_count == 1
    assert metrics.total_fees == Decimal("0.10002")
    assert metrics.traded_notional == Decimal("200.04")
    assert metrics.realized_return == Decimal("-0.00010002")
