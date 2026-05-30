"""Tests for deterministic risk and portfolio controls."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from tiko.domain.account import SimAccount
from tiko.domain.decision import TradeIntent
from tiko.services.portfolio import PortfolioService
from tiko.services.risk import RiskService


def create_intent(
    target_weight: Decimal = Decimal("0.10"),
    confidence: float = 0.8,
    data_quality_score: float = 1.0,
) -> TradeIntent:
    """Create a trade intent for risk tests.

    Args:
        target_weight: Requested target portfolio weight.
        confidence: Agent confidence.
        data_quality_score: Data quality score.

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
        max_leverage=Decimal("1"),
        confidence=confidence,
        expected_holding_period="1h",
        thesis="Risk control test intent.",
        evidence=[],
        invalidation_conditions=[],
        data_quality_score=data_quality_score,
        created_at_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_account() -> SimAccount:
    """Create a simulated account for portfolio tests.

    Returns:
        Simulated account domain model.
    """

    return SimAccount(
        account_id=uuid4(),
        name="risk-account",
        initial_equity=Decimal("100000"),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
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

    order_request = PortfolioService().create_order_request(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )

    assert order_request is not None
    assert order_request.side == "buy"
    assert order_request.quantity == Decimal("10.000000")


def test_portfolio_does_not_execute_rejected_review() -> None:
    """Verify rejected risk reviews cannot create simulated orders."""

    intent = create_intent(confidence=0.1)
    review = RiskService(minimum_confidence=0.5).review(intent)

    order_request = PortfolioService().create_order_request(
        account=create_account(),
        intent=intent,
        risk_review=review,
        reference_price=Decimal("100"),
    )

    assert order_request is None
