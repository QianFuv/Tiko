"""Tests for simulated exchange execution components."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from tiko.domain.order import OrderRequest
from tiko.simulation.broker import SimBroker
from tiko.simulation.fee import FeeEngine
from tiko.simulation.matching import MatchingEngine
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
