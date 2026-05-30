"""Tests for simulated exchange execution components."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from tiko.domain.account import SimAccount
from tiko.domain.order import OrderRequest
from tiko.domain.simulation import SimulationRun
from tiko.simulation.broker import SimBroker
from tiko.simulation.fee import FeeEngine
from tiko.simulation.ledger import apply_fill_to_account, apply_fill_to_ledger
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
    assert ledger_update.account.realized_pnl == Decimal("-0.10002")


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
