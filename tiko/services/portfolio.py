"""Portfolio sizing service for approved simulated trade intent."""

from collections.abc import Sequence
from decimal import ROUND_DOWN, Decimal

from tiko.domain.account import Position, SimAccount
from tiko.domain.decision import TradeIntent
from tiko.domain.order import OrderRequest
from tiko.domain.portfolio import PortfolioOrderPlan
from tiko.domain.risk import RiskReview


class PortfolioService:
    """Convert approved target exposure into internal simulated orders."""

    def __init__(
        self,
        lot_size: Decimal = Decimal("0.000001"),
        taker_fee_bps: Decimal = Decimal("5"),
        estimated_slippage_bps: Decimal = Decimal("2"),
    ) -> None:
        """Initialize sizing precision.

        Args:
            lot_size: Quantity precision used for simulated orders.
            taker_fee_bps: Estimated taker fee in basis points.
            estimated_slippage_bps: Estimated market slippage in basis points.
        """

        self.lot_size = lot_size
        self.taker_fee_bps = taker_fee_bps
        self.estimated_slippage_bps = estimated_slippage_bps

    def create_order_plan(
        self,
        account: SimAccount,
        intent: TradeIntent,
        risk_review: RiskReview,
        reference_price: Decimal,
        positions: Sequence[Position] = (),
    ) -> PortfolioOrderPlan:
        """Create a portfolio order sizing plan.

        Args:
            account: Current simulated account.
            intent: Structured trade intent.
            risk_review: Independent risk review.
            reference_price: Current market reference price.
            positions: Current simulated positions used for target-delta sizing.

        Returns:
            Portfolio sizing plan with optional order request.
        """

        target_notional = risk_review.approved_target_weight * account.total_equity
        current_notional = self._current_signed_notional(intent.symbol, positions)
        delta_notional = target_notional - current_notional
        if risk_review.status not in {"approved", "resized"}:
            return self._build_no_order_plan(
                account=account,
                intent=intent,
                reason="risk_review_not_executable",
                sizing_explanation=(
                    f"Risk review status {risk_review.status} cannot create orders."
                ),
                target_notional=target_notional,
                current_notional=current_notional,
                delta_notional=delta_notional,
                approved_delta_notional=Decimal("0"),
                reference_price=reference_price,
            )
        approved_delta_notional = delta_notional
        if abs(delta_notional) > risk_review.max_order_notional:
            approved_delta_notional = (
                risk_review.max_order_notional
                if delta_notional > Decimal("0")
                else -risk_review.max_order_notional
            )
        if approved_delta_notional == Decimal("0"):
            return self._build_no_order_plan(
                account=account,
                intent=intent,
                reason="target_exposure_already_met",
                sizing_explanation="Current exposure already matches target exposure.",
                target_notional=target_notional,
                current_notional=current_notional,
                delta_notional=delta_notional,
                approved_delta_notional=approved_delta_notional,
                reference_price=reference_price,
            )
        quantity = (abs(approved_delta_notional) / reference_price).quantize(
            self.lot_size, rounding=ROUND_DOWN
        )
        if quantity <= Decimal("0"):
            return self._build_no_order_plan(
                account=account,
                intent=intent,
                reason="quantity_below_lot_size",
                sizing_explanation="Rounded order quantity is below lot size.",
                target_notional=target_notional,
                current_notional=current_notional,
                delta_notional=delta_notional,
                approved_delta_notional=approved_delta_notional,
                reference_price=reference_price,
            )
        order_request = OrderRequest(
            run_id=intent.run_id,
            account_id=account.account_id,
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            side="buy" if approved_delta_notional > Decimal("0") else "sell",
            order_type="market",
            quantity=quantity,
            submitted_at_sim_time=intent.created_at_sim_time,
        )
        expected_notional = quantity * reference_price
        return PortfolioOrderPlan(
            run_id=intent.run_id,
            account_id=account.account_id,
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            status="order_created",
            reason=None,
            sizing_explanation=(
                f"Target notional {target_notional}; current notional "
                f"{current_notional}; approved delta {approved_delta_notional}; "
                f"rounded quantity {quantity} at reference price {reference_price}."
            ),
            target_notional=target_notional,
            current_notional=current_notional,
            delta_notional=delta_notional,
            approved_delta_notional=approved_delta_notional,
            reference_price=reference_price,
            quantity=quantity,
            expected_notional=expected_notional,
            estimated_fee=self._estimate_fee(expected_notional),
            estimated_slippage_bps=self.estimated_slippage_bps,
            order_request=order_request,
        )

    def create_order_request(
        self,
        account: SimAccount,
        intent: TradeIntent,
        risk_review: RiskReview,
        reference_price: Decimal,
        positions: Sequence[Position] = (),
    ) -> OrderRequest | None:
        """Create an internal order request for an approved risk review.

        Args:
            account: Current simulated account.
            intent: Structured trade intent.
            risk_review: Independent risk review.
            reference_price: Current market reference price.
            positions: Current simulated positions used for target-delta sizing.

        Returns:
            Simulated order request or `None` when no order should be created.
        """

        return self.create_order_plan(
            account=account,
            intent=intent,
            risk_review=risk_review,
            reference_price=reference_price,
            positions=positions,
        ).order_request

    def _build_no_order_plan(
        self,
        account: SimAccount,
        intent: TradeIntent,
        reason: str,
        sizing_explanation: str,
        target_notional: Decimal,
        current_notional: Decimal,
        delta_notional: Decimal,
        approved_delta_notional: Decimal,
        reference_price: Decimal,
    ) -> PortfolioOrderPlan:
        """Build a no-order portfolio plan.

        Args:
            account: Current simulated account.
            intent: Structured trade intent.
            reason: Machine-readable no-order reason.
            sizing_explanation: Human-readable sizing explanation.
            target_notional: Signed target notional.
            current_notional: Signed current notional.
            delta_notional: Signed raw delta notional.
            approved_delta_notional: Signed executable delta notional.
            reference_price: Current market reference price.

        Returns:
            Portfolio plan without an order request.
        """

        return PortfolioOrderPlan(
            run_id=intent.run_id,
            account_id=account.account_id,
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            status="no_order",
            reason=reason,
            sizing_explanation=sizing_explanation,
            target_notional=target_notional,
            current_notional=current_notional,
            delta_notional=delta_notional,
            approved_delta_notional=approved_delta_notional,
            reference_price=reference_price,
            quantity=Decimal("0"),
            expected_notional=Decimal("0"),
            estimated_fee=Decimal("0"),
            estimated_slippage_bps=Decimal("0"),
            order_request=None,
        )

    def _estimate_fee(self, expected_notional: Decimal) -> Decimal:
        """Estimate taker fee for an expected order notional.

        Args:
            expected_notional: Absolute expected order notional.

        Returns:
            Estimated fee amount.
        """

        return expected_notional * self.taker_fee_bps / Decimal("10000")

    def _current_signed_notional(
        self,
        symbol: str,
        positions: Sequence[Position],
    ) -> Decimal:
        """Calculate current signed notional for one symbol.

        Args:
            symbol: Symbol to match.
            positions: Current simulated positions.

        Returns:
            Signed notional where longs are positive and shorts are negative.
        """

        return sum(
            (
                position.notional if position.side == "long" else -position.notional
                for position in positions
                if position.symbol == symbol and position.side != "flat"
            ),
            Decimal("0"),
        )
