"""Tests for simulated exchange execution components."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

import pytest

from tiko.domain.account import Position, SimAccount
from tiko.domain.order import Fill, OrderRequest
from tiko.domain.simulation import SimulationRun
from tiko.simulation.broker import SimBroker
from tiko.simulation.fee import FeeEngine
from tiko.simulation.ledger import (
    InsufficientCashError,
    apply_fill_to_account,
    apply_fill_to_ledger,
    apply_funding_to_ledger,
    calculate_fill_accounting,
)
from tiko.simulation.matching import MatchingEngine
from tiko.simulation.metrics import MetricsEngine
from tiko.simulation.slippage import SlippageContext, SlippageEngine


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


def test_slippage_engine_calculates_contextual_market_slippage() -> None:
    """Verify contextual slippage uses volatility, spread, size, and depth."""

    engine = SlippageEngine(
        slippage_bps=Decimal("2"),
        volatility_multiplier=Decimal("0.2"),
        liquidity_multiplier=Decimal("1.5"),
    )
    context = SlippageContext(
        volatility_bps=Decimal("10"),
        spread_bps=Decimal("4"),
        order_notional=Decimal("200"),
        depth_1pct_usd=Decimal("10000"),
    )

    assert engine.calculate_market_slippage_bps(context) == Decimal("9")
    assert engine.apply_market_slippage(Decimal("100"), "buy", context) == Decimal(
        "100.09"
    )
    assert engine.apply_market_slippage(Decimal("100"), "sell", context) == Decimal(
        "99.91"
    )


def test_slippage_engine_skips_liquidity_impact_without_depth() -> None:
    """Verify missing or zero depth does not add liquidity impact."""

    engine = SlippageEngine(
        slippage_bps=Decimal("2"),
        volatility_multiplier=Decimal("0.2"),
        liquidity_multiplier=Decimal("1.5"),
    )
    context_without_depth = SlippageContext(
        volatility_bps=Decimal("10"),
        spread_bps=Decimal("4"),
        order_notional=Decimal("200"),
    )
    context_with_zero_depth = SlippageContext(
        volatility_bps=Decimal("10"),
        spread_bps=Decimal("4"),
        order_notional=Decimal("200"),
        depth_1pct_usd=Decimal("0"),
    )

    assert engine.calculate_market_slippage_bps(context_without_depth) == Decimal("6")
    assert engine.calculate_market_slippage_bps(context_with_zero_depth) == Decimal("6")


def test_matching_engine_creates_filled_order_and_fill() -> None:
    """Verify market matching creates linked order and fill records."""

    order, fill = MatchingEngine().match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
    )

    assert order.status == "filled"
    assert fill is not None
    assert order.order_id == fill.order_id
    assert fill.price == Decimal("100.02")
    assert fill.fee == Decimal("0.10002")
    assert fill.slippage_bps == Decimal("2")


def test_matching_engine_records_contextual_slippage_bps() -> None:
    """Verify market fills record the effective contextual slippage."""

    context = SlippageContext(
        volatility_bps=Decimal("10"),
        spread_bps=Decimal("4"),
        order_notional=Decimal("200"),
        depth_1pct_usd=Decimal("10000"),
    )

    order, fill = MatchingEngine(
        slippage_engine=SlippageEngine(
            slippage_bps=Decimal("2"),
            volatility_multiplier=Decimal("0.2"),
            liquidity_multiplier=Decimal("1.5"),
        )
    ).match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
        slippage_context=context,
    )

    assert order.status == "filled"
    assert fill is not None
    assert fill.price == Decimal("100.09")
    assert fill.fee == Decimal("0.10009")
    assert fill.slippage_bps == Decimal("9")


def test_matching_engine_rejects_market_order_when_spread_exceeds_limit() -> None:
    """Verify market orders reject when spread violates exchange guards."""

    order, fill = MatchingEngine(
        max_market_spread_bps=Decimal("10")
    ).match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
        slippage_context=SlippageContext(
            spread_bps=Decimal("11"),
            depth_1pct_usd=Decimal("1000"),
        ),
    )

    assert order.status == "rejected"
    assert fill is None


def test_matching_engine_rejects_market_order_when_depth_is_insufficient() -> None:
    """Verify market orders reject when available depth is too low."""

    order, fill = MatchingEngine(
        min_market_depth_1pct_usd=Decimal("1000")
    ).match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
        slippage_context=SlippageContext(
            spread_bps=Decimal("2"),
            depth_1pct_usd=Decimal("999"),
        ),
    )

    assert order.status == "rejected"
    assert fill is None


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


def test_matching_engine_expires_uncrossed_ioc_limit_order() -> None:
    """Verify uncrossed IOC limit orders expire without fills."""

    order, fill = MatchingEngine().match_limit_order(
        create_limit_order_request("buy", Decimal("99")),
        reference_price=Decimal("100"),
        time_in_force="ioc",
    )

    assert order.status == "expired"
    assert order.limit_price == Decimal("99")
    assert fill is None


def test_matching_engine_partially_fills_limit_order_by_available_depth() -> None:
    """Verify crossed limit orders cap fill quantity by simulated depth."""

    order, fill = MatchingEngine(
        maker_fee_engine=FeeEngine(fee_bps=Decimal("2")),
    ).match_limit_order(
        create_limit_order_request("buy", Decimal("101")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0.5"),
    )

    assert fill is not None
    assert order.status == "partially_filled"
    assert order.quantity == Decimal("2")
    assert fill.quantity == Decimal("0.5")
    assert fill.price == Decimal("100")
    assert fill.fee == Decimal("0.01")


def test_matching_engine_partially_fills_ioc_limit_order_by_available_depth() -> None:
    """Verify IOC limit orders can partially fill from available depth."""

    order, fill = MatchingEngine(
        maker_fee_engine=FeeEngine(fee_bps=Decimal("2")),
    ).match_limit_order(
        create_limit_order_request("buy", Decimal("101")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0.5"),
        time_in_force="ioc",
    )

    assert fill is not None
    assert order.status == "partially_filled"
    assert fill.quantity == Decimal("0.5")
    assert fill.price == Decimal("100")
    assert fill.fee == Decimal("0.01")


def test_matching_engine_keeps_crossed_limit_open_without_available_depth() -> None:
    """Verify crossed limit orders do not fill when simulated depth is zero."""

    order, fill = MatchingEngine().match_limit_order(
        create_limit_order_request("buy", Decimal("101")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0"),
    )

    assert order.status == "open"
    assert fill is None


def test_matching_engine_expires_unfilled_ioc_limit_order_without_depth() -> None:
    """Verify crossed IOC limit orders expire when no depth is available."""

    order, fill = MatchingEngine().match_limit_order(
        create_limit_order_request("buy", Decimal("101")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0"),
        time_in_force="ioc",
    )

    assert order.status == "expired"
    assert fill is None


def test_matching_engine_expires_fok_limit_order_when_depth_is_insufficient() -> None:
    """Verify FOK limit orders expire when full quantity is unavailable."""

    order, fill = MatchingEngine().match_limit_order(
        create_limit_order_request("buy", Decimal("101")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0.5"),
        time_in_force="fok",
    )

    assert order.status == "expired"
    assert fill is None


def test_matching_engine_rejects_negative_available_depth() -> None:
    """Verify limit matching rejects impossible negative simulated depth."""

    with pytest.raises(ValueError, match="available_quantity"):
        MatchingEngine().match_limit_order(
            create_limit_order_request("buy", Decimal("101")),
            reference_price=Decimal("100"),
            available_quantity=Decimal("-1"),
        )


def test_matching_engine_rejects_unsupported_time_in_force() -> None:
    """Verify limit matching rejects unsupported expiry policies."""

    unsupported_time_in_force: Any = "day"

    with pytest.raises(ValueError, match="time_in_force"):
        MatchingEngine().match_limit_order(
            create_limit_order_request("buy", Decimal("101")),
            reference_price=Decimal("100"),
            time_in_force=unsupported_time_in_force,
        )


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
    assert fill is not None
    assert fill.price == Decimal("99.98")
    assert fill.fee == Decimal("0.09998")
    assert fill.order_id == order.order_id


def test_sim_broker_rejects_market_orders_when_disabled() -> None:
    """Verify broker market permission can reject simulated orders."""

    order, fill = SimBroker(allow_market=False).submit_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
    )

    assert order.status == "rejected"
    assert order.order_type == "market"
    assert fill is None


def test_sim_broker_passes_slippage_context_to_market_matching() -> None:
    """Verify broker market submissions pass slippage context to matching."""

    context = SlippageContext(
        volatility_bps=Decimal("2"),
        spread_bps=Decimal("4"),
        order_notional=Decimal("100"),
        depth_1pct_usd=Decimal("10000"),
    )

    order, fill = SimBroker(
        slippage_bps=Decimal("1"),
        slippage_volatility_multiplier=Decimal("1"),
        slippage_liquidity_multiplier=Decimal("1"),
    ).submit_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
        slippage_context=context,
    )

    assert order.status == "filled"
    assert fill is not None
    assert fill.price == Decimal("100.06")
    assert fill.slippage_bps == Decimal("6")


def test_sim_broker_passes_market_depth_guard_to_matching() -> None:
    """Verify broker market submissions can reject on missing depth."""

    order, fill = SimBroker(
        min_market_depth_1pct_usd=Decimal("1000"),
    ).submit_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
        slippage_context=SlippageContext(spread_bps=Decimal("2")),
    )

    assert order.status == "rejected"
    assert fill is None


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


def test_sim_broker_rejects_limit_orders_when_disabled() -> None:
    """Verify broker limit permission can reject simulated orders."""

    order, fill = SimBroker(allow_limit=False).submit_limit_order(
        create_limit_order_request("sell", Decimal("99")),
        reference_price=Decimal("100"),
    )

    assert order.status == "rejected"
    assert order.order_type == "limit"
    assert order.limit_price == Decimal("99")
    assert fill is None


def test_sim_broker_passes_available_depth_to_limit_matching() -> None:
    """Verify broker limit submissions can produce partial fills."""

    order, fill = SimBroker(
        fee_bps=Decimal("5"),
        maker_fee_bps=Decimal("2"),
    ).submit_limit_order(
        create_limit_order_request("sell", Decimal("99")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0.25"),
    )

    assert fill is not None
    assert order.status == "partially_filled"
    assert fill.quantity == Decimal("0.25")
    assert fill.fee == Decimal("0.005")


def test_sim_broker_passes_time_in_force_to_limit_matching() -> None:
    """Verify broker limit submissions pass time-in-force to matching."""

    order, fill = SimBroker().submit_limit_order(
        create_limit_order_request("sell", Decimal("99")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0.25"),
        time_in_force="fok",
    )

    assert order.status == "expired"
    assert fill is None


def test_sim_broker_retains_unfilled_gtc_limit_orders() -> None:
    """Verify GTC limit orders stay open when they do not cross."""

    broker = SimBroker()

    order, fill = broker.submit_limit_order(
        create_limit_order_request("buy", Decimal("99")),
        reference_price=Decimal("100"),
    )

    assert order.status == "open"
    assert fill is None
    assert broker.list_open_orders() == (order,)


def test_sim_broker_reevaluates_open_gtc_limit_orders() -> None:
    """Verify later prices can fill retained GTC limit orders."""

    broker = SimBroker()
    order, fill = broker.submit_limit_order(
        create_limit_order_request("buy", Decimal("99")),
        reference_price=Decimal("100"),
    )
    fill_time = datetime(2026, 1, 1, 1, tzinfo=UTC)

    results = broker.reevaluate_open_orders(
        reference_price=Decimal("98"),
        as_of=fill_time,
    )

    updated_order, later_fill = results[0]
    assert fill is None
    assert updated_order.order_id == order.order_id
    assert updated_order.status == "filled"
    assert updated_order.updated_at_sim_time == fill_time
    assert later_fill is not None
    assert later_fill.order_id == order.order_id
    assert later_fill.price == Decimal("98")
    assert later_fill.quantity == Decimal("2")
    assert later_fill.filled_at_sim_time == fill_time
    assert broker.list_open_orders() == ()


def test_sim_broker_continues_partially_filled_gtc_limit_orders() -> None:
    """Verify partially filled GTC orders retain only remaining quantity."""

    broker = SimBroker(
        fee_bps=Decimal("5"),
        maker_fee_bps=Decimal("2"),
    )
    order, first_fill = broker.submit_limit_order(
        create_limit_order_request("sell", Decimal("99")),
        reference_price=Decimal("100"),
        available_quantity=Decimal("0.25"),
    )
    fill_time = datetime(2026, 1, 1, 1, tzinfo=UTC)

    results = broker.reevaluate_open_orders(
        reference_price=Decimal("100"),
        as_of=fill_time,
        available_quantity=Decimal("1.75"),
    )

    updated_order, second_fill = results[0]
    assert first_fill is not None
    assert first_fill.quantity == Decimal("0.25")
    assert broker.list_open_orders() == ()
    assert updated_order.order_id == order.order_id
    assert updated_order.status == "filled"
    assert second_fill is not None
    assert second_fill.order_id == order.order_id
    assert second_fill.quantity == Decimal("1.75")
    assert second_fill.fee == Decimal("0.035")


def test_sim_broker_cancels_open_limit_orders() -> None:
    """Verify broker cancellation removes retained open orders."""

    broker = SimBroker()
    first_order, _first_fill = broker.submit_limit_order(
        create_limit_order_request("buy", Decimal("99")),
        reference_price=Decimal("100"),
    )
    second_order, _second_fill = broker.submit_limit_order(
        create_limit_order_request("buy", Decimal("98")),
        reference_price=Decimal("100"),
    )
    cancel_time = datetime(2026, 1, 1, 1, tzinfo=UTC)
    cancel_all_time = datetime(2026, 1, 1, 2, tzinfo=UTC)

    canceled_order = broker.cancel_order(first_order.order_id, cancel_time)
    canceled_orders = broker.cancel_all_orders(cancel_all_time)

    assert canceled_order.order_id == first_order.order_id
    assert canceled_order.status == "canceled"
    assert canceled_order.updated_at_sim_time == cancel_time
    assert broker.list_open_orders() == ()
    assert canceled_orders == (
        second_order.model_copy(
            update={
                "status": "canceled",
                "updated_at_sim_time": cancel_all_time,
            }
        ),
    )


def test_ledger_update_preserves_account_output_and_exposes_metadata() -> None:
    """Verify ledger metadata matches the account update path."""

    account = create_account()
    _order, fill = MatchingEngine().match_market_order(
        create_order_request("buy"),
        reference_price=Decimal("100"),
    )

    assert fill is not None
    ledger_update = apply_fill_to_ledger(account, fill)

    assert apply_fill_to_account(account, fill) == ledger_update.account
    assert ledger_update.notional == Decimal("200.04")
    assert ledger_update.fee == Decimal("0.10002")
    assert ledger_update.cash_delta == Decimal("-200.14002")
    assert ledger_update.realized_pnl_delta == Decimal("-0.10002")
    assert ledger_update.account.realized_pnl == Decimal("-0.10002")


def test_ledger_rejects_buy_fill_when_cash_is_insufficient() -> None:
    """Verify buy fills cannot overdraw simulated cash."""

    account = create_account().model_copy(
        update={
            "cash_balance": Decimal("5"),
            "total_equity": Decimal("5"),
        }
    )
    fill = Fill(
        fill_id=uuid4(),
        order_id=uuid4(),
        run_id=uuid4(),
        symbol="BTCUSDT",
        side="buy",
        quantity=Decimal("1"),
        price=Decimal("10"),
        fee=Decimal("1"),
        slippage_bps=Decimal("0"),
        filled_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(InsufficientCashError):
        apply_fill_to_ledger(account, fill)


def test_funding_update_preserves_negative_account_values() -> None:
    """Verify funding accounting does not clamp negative cash or equity."""

    account = create_account().model_copy(
        update={
            "cash_balance": Decimal("0.05"),
            "total_equity": Decimal("0.05"),
        }
    )

    update = apply_funding_to_ledger(
        account,
        [create_position("long")],
        Decimal("0.001"),
    )

    assert update.cash_delta == Decimal("-0.200")
    assert update.account.cash_balance == Decimal("-0.15")
    assert update.account.total_equity == Decimal("-0.15")


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
    assert fill is not None
    updated_account = apply_fill_to_account(account, fill)
    run = create_run(updated_account)

    metrics = MetricsEngine().summarize_execution(run, [order], [fill])

    assert metrics.run_id == run.run_id
    assert metrics.order_count == 1
    assert metrics.fill_count == 1
    assert metrics.total_fees == Decimal("0.10002")
    assert metrics.traded_notional == Decimal("200.04")
    assert metrics.realized_return == Decimal("-0.00010002")
