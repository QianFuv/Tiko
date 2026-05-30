"""Risk review service for structured trade intent."""

from decimal import Decimal
from uuid import uuid4

from tiko.domain.decision import TradeIntent
from tiko.domain.risk import RiskReview


class RiskService:
    """Apply deterministic risk rules before simulated order creation."""

    def __init__(self, minimum_confidence: float) -> None:
        """Initialize risk thresholds.

        Args:
            minimum_confidence: Minimum confidence required to approve an intent.
        """

        self.minimum_confidence = minimum_confidence

    def review(self, intent: TradeIntent) -> RiskReview:
        """Review a structured trade intent.

        Args:
            intent: Agent-generated trade intent.

        Returns:
            Risk review decision.
        """

        if intent.confidence < self.minimum_confidence:
            return RiskReview(
                review_id=uuid4(),
                decision_id=intent.decision_id,
                status="rejected",
                original_target_weight=intent.target_weight,
                approved_target_weight=Decimal("0"),
                max_order_notional=Decimal("0"),
                reasons=["confidence_below_threshold"],
                triggered_rules=["minimum_confidence"],
                created_at_sim_time=intent.created_at_sim_time,
            )
        return RiskReview(
            review_id=uuid4(),
            decision_id=intent.decision_id,
            status="approved",
            original_target_weight=intent.target_weight,
            approved_target_weight=intent.target_weight,
            max_order_notional=Decimal("1000000000"),
            reasons=[],
            triggered_rules=[],
            created_at_sim_time=intent.created_at_sim_time,
        )
