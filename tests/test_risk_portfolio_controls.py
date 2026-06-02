"""Tests for deterministic risk and portfolio controls."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

import pytest

from tiko.domain.account import Position, SimAccount
from tiko.domain.decision import TradeIntent
from tiko.domain.market import OrderBookSnapshot
from tiko.domain.order import SimOrder
from tiko.domain.risk import RiskContext
from tiko.services.portfolio import PortfolioService
from tiko.services.risk import RiskService


def create_intent(
    target_weight: Decimal = Decimal("0.10"),
    confidence: float = 0.8,
    data_quality_score: float = 1.0,
    max_leverage: Decimal = Decimal("1"),
) -> TradeIntent:
    """Create a trade intent for risk tests.

    Args:
        target_weight: Requested target portfolio weight.
        confidence: Agent confidence.
        data_quality_score: Data quality score.
        max_leverage: Requested maximum leverage.

    Returns:
        Trade intent domain model.
    """

    return TradeIntent(
        decision_id=uuid4(),
        run_id=uuid4(),
        agent_id="risk-test",
        symbol="BTCUSDT",
        market_type="synthetic",
        action="open_long" if target_weight >= Decimal("0") else "open_short",
        target_weight=target_weight,
        max_leverage=max_leverage,
        confidence=confidence,
        expected_holding_period="1h",
        thesis="Risk control test intent.",
        evidence=[],
        invalidation_conditions=[],
        data_quality_score=data_quality_score,
        created_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_account(
    realized_pnl: Decimal = Decimal("0"),
    max_drawdown: Decimal = Decimal("0"),
) -> SimAccount:
    """Create a simulated account for portfolio tests.

    Args:
        realized_pnl: Realized PnL value.
        max_drawdown: Max drawdown value.

    Returns:
        Simulated account domain model.
    """

    return SimAccount(
        account_id=uuid4(),
        name="risk-account",
        initial_equity=Decimal("100000"),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
        realized_pnl=realized_pnl,
        unrealized_pnl=Decimal("0"),
        max_drawdown=max_drawdown,
        status="active",
    )


def create_position(
    side: Literal["long", "short"],
    notional: Decimal,
    symbol: str = "BTCUSDT",
) -> Position:
    """Create a marked position for portfolio sizing tests.

    Args:
        side: Position side.
        notional: Absolute position notional.
        symbol: Position symbol.

    Returns:
        Position domain model.
    """

    return Position(
        position_id=uuid4(),
        account_id=uuid4(),
        symbol=symbol,
        side=side,
        quantity=notional / Decimal("100"),
        avg_entry_price=Decimal("100"),
        mark_price=Decimal("100"),
        notional=notional,
        leverage=Decimal("1"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        liquidation_price=None,
        updated_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_open_order(notional: Decimal) -> SimOrder:
    """Create an open limit order for risk context tests.

    Args:
        notional: Order notional at the limit price.

    Returns:
        Simulated open order.
    """

    limit_price = Decimal("100")
    return SimOrder(
        order_id=uuid4(),
        run_id=uuid4(),
        account_id=uuid4(),
        decision_id=uuid4(),
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        quantity=notional / limit_price,
        limit_price=limit_price,
        status="open",
        submitted_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_orderbook(spread_bps: Decimal, depth_1pct_usd: Decimal) -> OrderBookSnapshot:
    """Create an orderbook snapshot for risk context tests.

    Args:
        spread_bps: Snapshot spread in basis points.
        depth_1pct_usd: Snapshot one-percent depth.

    Returns:
        Orderbook snapshot.
    """

    return OrderBookSnapshot(
        symbol="BTCUSDT",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        bids=[(Decimal("99"), Decimal("1"))],
        asks=[(Decimal("101"), Decimal("1"))],
        mid_price=Decimal("100"),
        spread_bps=spread_bps,
        depth_1pct_usd=depth_1pct_usd,
        source="test",
    )


def test_risk_rejects_low_confidence_and_low_data_quality() -> None:
    """Verify rejection reasons are explicit and non-executable."""

    review = RiskService(
        minimum_confidence=0.6,
        minimum_data_quality_score=0.8,
    ).review(create_intent(confidence=0.5, data_quality_score=0.7))

    assert review.status == "rejected"
    assert review.approved_target_weight == Decimal("0")
    assert review.max_order_notional == Decimal("0")
    assert review.reasons == [
        "confidence_below_threshold",
        "data_quality_below_threshold",
    ]


def test_risk_rejects_excess_leverage() -> None:
    """Verify risk review blocks intents above the run leverage ceiling."""

    review = RiskService(
        minimum_confidence=0.6,
        max_leverage=Decimal("2"),
    ).review(create_intent(max_leverage=Decimal("3")))

    assert review.status == "rejected"
    assert review.approved_target_weight == Decimal("0")
    assert review.max_order_notional == Decimal("0")
    assert review.reasons == ["leverage_exceeds_limit"]
    assert review.triggered_rules == ["max_leverage"]


def test_risk_rejects_short_exposure_when_disabled() -> None:
    """Verify risk review blocks short exposure when broker config forbids it."""

    review = RiskService(
        minimum_confidence=0.6,
        allow_short=False,
    ).review(create_intent(target_weight=Decimal("-0.10")))

    assert review.status == "rejected"
    assert review.approved_target_weight == Decimal("0")
    assert review.max_order_notional == Decimal("0")
    assert review.reasons == ["short_exposure_not_allowed"]
    assert review.triggered_rules == ["allow_short"]


def test_risk_rejects_leverage_when_disabled() -> None:
    """Verify risk review blocks leverage when broker config forbids it."""

    review = RiskService(
        minimum_confidence=0.6,
        max_leverage=Decimal("3"),
        allow_leverage=False,
    ).review(create_intent(max_leverage=Decimal("2")))

    assert review.status == "rejected"
    assert review.approved_target_weight == Decimal("0")
    assert review.max_order_notional == Decimal("0")
    assert review.reasons == ["leverage_not_allowed"]
    assert review.triggered_rules == ["allow_leverage"]


def test_risk_rejects_context_exposure_breaches() -> None:
    """Verify risk context can block gross and net exposure breaches."""

    review = RiskService(
        minimum_confidence=0.6,
        max_gross_exposure=Decimal("1.0"),
        max_net_exposure=Decimal("1.0"),
    ).review(
        create_intent(target_weight=Decimal("0.30")),
        account=create_account(),
        context=RiskContext(
            positions=[create_position("long", Decimal("90000"), symbol="ETHUSDT")]
        ),
    )

    assert review.status == "rejected"
    assert review.approved_target_weight == Decimal("0")
    assert review.reasons == [
        "gross_exposure_exceeds_limit",
        "net_exposure_exceeds_limit",
    ]
    assert review.triggered_rules == ["max_gross_exposure", "max_net_exposure"]


def test_risk_rejects_open_order_exposure_breaches() -> None:
    """Verify active open orders count against configured exposure limits."""

    review = RiskService(
        minimum_confidence=0.6,
        max_open_order_exposure=Decimal("0.50"),
    ).review(
        create_intent(target_weight=Decimal("0.10")),
        account=create_account(),
        context=RiskContext(open_orders=[create_open_order(Decimal("60000"))]),
    )

    assert review.status == "rejected"
    assert review.reasons == ["open_order_exposure_exceeds_limit"]
    assert review.triggered_rules == ["max_open_order_exposure"]


def test_risk_rejects_liquidity_context_breaches() -> None:
    """Verify spread and depth context can block risky intents."""

    review = RiskService(
        minimum_confidence=0.6,
        max_spread_bps=Decimal("20"),
        min_depth_1pct_usd=Decimal("500000"),
    ).review(
        create_intent(target_weight=Decimal("0.10")),
        account=create_account(),
        context=RiskContext(
            latest_orderbook=create_orderbook(
                spread_bps=Decimal("25"),
                depth_1pct_usd=Decimal("100000"),
            )
        ),
    )

    assert review.status == "rejected"
    assert review.reasons == ["spread_exceeds_limit", "depth_below_minimum"]
    assert review.triggered_rules == ["max_spread_bps", "min_depth_1pct_usd"]


def test_risk_resizes_oversized_long_and_short_intents() -> None:
    """Verify oversized signed target weights are capped by risk."""

    risk_service = RiskService(
        minimum_confidence=0.5,
        minimum_data_quality_score=0.8,
        max_target_weight=Decimal("0.25"),
        max_order_notional=Decimal("1000"),
    )

    long_review = risk_service.review(create_intent(target_weight=Decimal("0.50")))
    short_review = risk_service.review(create_intent(target_weight=Decimal("-0.50")))

    assert long_review.status == "resized"
    assert long_review.approved_target_weight == Decimal("0.25")
    assert short_review.status == "resized"
    assert short_review.approved_target_weight == Decimal("-0.25")


def test_portfolio_executes_resized_review_with_notional_cap() -> None:
    """Verify portfolio sizing uses only risk-approved notional."""

    intent = create_intent(target_weight=Decimal("0.50"))
    review = RiskService(
        minimum_confidence=0.5,
        minimum_data_quality_score=0.8,
        max_target_weight=Decimal("0.25"),
        max_order_notional=Decimal("1000"),
    ).review(intent)

    plan = PortfolioService().create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )
    order_request = plan.order_request

    assert plan.status == "order_created"
    assert plan.expected_notional == Decimal("1000.000000")
    assert plan.estimated_fee == Decimal("0.500000")
    assert plan.estimated_slippage_bps == Decimal("2")
    assert "approved delta 1000" in plan.sizing_explanation
    assert order_request is not None
    assert order_request.order_type == "market"
    assert order_request.limit_price is None
    assert order_request.side == "buy"
    assert order_request.quantity == Decimal("10.000000")


def test_portfolio_creates_limit_order_with_maker_fee_estimate() -> None:
    """Verify configured limit plans carry a limit price and maker fee estimate."""

    intent = create_intent(target_weight=Decimal("0.10"))
    review = RiskService(minimum_confidence=0.5).review(intent)

    plan = PortfolioService(
        taker_fee_bps=Decimal("5"),
        maker_fee_bps=Decimal("2"),
        order_type="limit",
    ).create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )
    order_request = plan.order_request

    assert plan.status == "order_created"
    assert plan.expected_notional == Decimal("10000.000000")
    assert plan.estimated_fee == Decimal("2.000000")
    assert order_request is not None
    assert order_request.order_type == "limit"
    assert order_request.limit_price == Decimal("100")


def test_portfolio_rejects_invalid_order_type_configuration() -> None:
    """Verify unsupported order type configuration fails before planning."""

    invalid_order_type: Any = "stop"

    with pytest.raises(ValueError, match="order_type"):
        PortfolioService(order_type=invalid_order_type)


def test_portfolio_skips_order_when_current_exposure_matches_target() -> None:
    """Verify portfolio sizing does not duplicate existing target exposure."""

    intent = create_intent(target_weight=Decimal("0.10"))
    review = RiskService(minimum_confidence=0.5).review(intent)

    plan = PortfolioService().create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
        positions=[create_position("long", Decimal("10000"))],
    )

    assert plan.status == "no_order"
    assert plan.reason == "target_exposure_already_met"
    assert plan.order_request is None


def test_portfolio_reduces_excess_long_exposure() -> None:
    """Verify portfolio sizing sells only the delta above the target."""

    intent = create_intent(target_weight=Decimal("0.10"))
    review = RiskService(minimum_confidence=0.5).review(intent)

    order_request = PortfolioService().create_order_request(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
        positions=[create_position("long", Decimal("15000"))],
    )

    assert order_request is not None
    assert order_request.side == "sell"
    assert order_request.quantity == Decimal("50.000000")


def test_portfolio_caps_reversal_delta_order() -> None:
    """Verify portfolio sizing caps close-plus-reversal delta orders."""

    intent = create_intent(target_weight=Decimal("-0.10"))
    review = RiskService(
        minimum_confidence=0.5,
        max_order_notional=Decimal("1000"),
    ).review(intent)

    order_request = PortfolioService().create_order_request(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
        positions=[create_position("long", Decimal("5000"))],
    )

    assert order_request is not None
    assert order_request.side == "sell"
    assert order_request.quantity == Decimal("10.000000")


def test_portfolio_does_not_execute_rejected_review() -> None:
    """Verify rejected risk reviews cannot create simulated orders."""

    intent = create_intent(confidence=0.1)
    review = RiskService(minimum_confidence=0.5).review(intent)

    plan = PortfolioService().create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )

    assert plan.status == "no_order"
    assert plan.reason == "risk_review_not_executable"
    assert plan.order_request is None


def test_portfolio_plan_skips_quantity_below_lot_size() -> None:
    """Verify portfolio plan explains rounded zero-quantity orders."""

    intent = create_intent(target_weight=Decimal("0.000001"))
    review = RiskService(minimum_confidence=0.5).review(intent)

    plan = PortfolioService(lot_size=Decimal("1")).create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("1000000"),
    )

    assert plan.status == "no_order"
    assert plan.reason == "quantity_below_lot_size"
    assert plan.order_request is None


def test_portfolio_plan_skips_notional_below_minimum() -> None:
    """Verify portfolio plan blocks orders below minimum executable notional."""

    intent = create_intent(target_weight=Decimal("0.00001"))
    review = RiskService(minimum_confidence=0.5).review(intent)

    plan = PortfolioService(min_order_notional=Decimal("5")).create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )

    assert plan.status == "no_order"
    assert plan.reason == "notional_below_minimum"
    assert "below minimum order notional 5" in plan.sizing_explanation
    assert plan.order_request is None


def test_portfolio_plan_allows_notional_equal_to_minimum() -> None:
    """Verify minimum notional is inclusive for executable orders."""

    intent = create_intent(target_weight=Decimal("0.10"))
    review = RiskService(minimum_confidence=0.5).review(intent)

    plan = PortfolioService(
        min_order_notional=Decimal("10000.000000")
    ).create_order_plan(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )

    assert plan.status == "order_created"
    assert plan.expected_notional == Decimal("10000.000000")
    assert plan.order_request is not None


def test_portfolio_rejects_negative_min_order_notional() -> None:
    """Verify minimum notional configuration cannot be negative."""

    with pytest.raises(ValueError, match="min_order_notional"):
        PortfolioService(min_order_notional=Decimal("-1"))


def test_risk_circuit_breakers_block_loss_and_drawdown_breaches() -> None:
    """Verify account-state circuit breakers stop simulated execution."""

    risk_service = RiskService(
        minimum_confidence=0.5,
        max_daily_loss=Decimal("0.01"),
        max_drawdown=Decimal("0.05"),
    )

    loss_review = risk_service.review(
        create_intent(),
        account=create_account(realized_pnl=Decimal("-1500")),
    )
    drawdown_review = risk_service.review(
        create_intent(),
        account=create_account(max_drawdown=Decimal("-0.08")),
    )
    order_request = PortfolioService().create_order_request(
        account=create_account(realized_pnl=Decimal("-1500")),
        intent=create_intent(),
        risk_review=loss_review,
        reference_price=Decimal("100"),
    )

    assert loss_review.status == "circuit_blocked"
    assert loss_review.approved_target_weight == Decimal("0")
    assert loss_review.max_order_notional == Decimal("0")
    assert loss_review.reasons == ["daily_loss_limit_exceeded"]
    assert loss_review.triggered_rules == ["max_daily_loss"]
    assert drawdown_review.status == "circuit_blocked"
    assert drawdown_review.reasons == ["drawdown_limit_exceeded"]
    assert drawdown_review.triggered_rules == ["max_drawdown"]
    assert order_request is None


def test_daily_loss_uses_context_bucket_when_available() -> None:
    """Verify daily loss checks prefer the point-in-time context bucket."""

    risk_service = RiskService(
        minimum_confidence=0.5,
        max_daily_loss=Decimal("0.01"),
    )

    cumulative_loss_review = risk_service.review(
        create_intent(),
        account=create_account(realized_pnl=Decimal("-1500")),
        context=RiskContext(daily_realized_pnl=Decimal("0")),
    )
    daily_loss_review = risk_service.review(
        create_intent(),
        account=create_account(realized_pnl=Decimal("0")),
        context=RiskContext(daily_realized_pnl=Decimal("-1500")),
    )

    assert cumulative_loss_review.status == "approved"
    assert cumulative_loss_review.reasons == []
    assert daily_loss_review.status == "circuit_blocked"
    assert daily_loss_review.reasons == ["daily_loss_limit_exceeded"]
    assert daily_loss_review.triggered_rules == ["max_daily_loss"]
