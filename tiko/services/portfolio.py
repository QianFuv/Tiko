"""Portfolio sizing service for approved simulated trade intent."""

from decimal import ROUND_DOWN, Decimal

from tiko.domain.account import SimAccount
from tiko.domain.decision import TradeIntent
from tiko.domain.order import OrderRequest
from tiko.domain.risk import RiskReview


class PortfolioService:
    """Convert approved target exposure into internal simulated orders."""

    def __init__(self, lot_size: Decimal = Decimal("0.000001")) -> None:
        """Initialize sizing precision.

        Args:
            lot_size: Quantity precision used for simulated orders.
        """

        self.lot_size = lot_size

    def create_order_request(
        self,
        account: SimAccount,
        intent: TradeIntent,
        risk_review: RiskReview,
        reference_price: Decimal,
    ) -> OrderRequest | None:
        """Create an internal order request for an approved risk review.

        Args:
            account: Current simulated account.
            intent: Structured trade intent.
            risk_review: Independent risk review.
            reference_price: Current market reference price.

        Returns:
            Simulated order request or `None` when no order should be created.
        """

        if risk_review.status not in {"approved", "resized"}:
            return None
        target_notional = risk_review.approved_target_weight * account.total_equity
        if abs(target_notional) > risk_review.max_order_notional:
            target_notional = (
                risk_review.max_order_notional
                if target_notional > Decimal("0")
                else -risk_review.max_order_notional
            )
        if target_notional == Decimal("0"):
            return None
        quantity = (abs(target_notional) / reference_price).quantize(
            self.lot_size, rounding=ROUND_DOWN
        )
        if quantity <= Decimal("0"):
            return None
        return OrderRequest(
            run_id=intent.run_id,
            account_id=account.account_id,
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            side="buy" if target_notional > Decimal("0") else "sell",
            order_type="market",
            quantity=quantity,
            submitted_at_sim_time=intent.created_at_sim_time,
        )
