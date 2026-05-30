"""Risk review service for structured trade intent."""

from decimal import Decimal
from typing import Literal
from uuid import uuid4

from tiko.domain.decision import TradeIntent
from tiko.domain.risk import RiskReview


class RiskService:
    """Apply deterministic risk rules before simulated order creation."""

    def __init__(
        self,
        minimum_confidence: float,
        minimum_data_quality_score: float = 0.0,
        max_target_weight: Decimal = Decimal("1"),
        max_order_notional: Decimal = Decimal("1000000000"),
    ) -> None:
        """Initialize risk thresholds.

        Args:
            minimum_confidence: Minimum confidence required to approve an intent.
            minimum_data_quality_score: Minimum data quality required.
            max_target_weight: Maximum absolute portfolio target weight.
            max_order_notional: Maximum simulated order notional.
        """

        self.minimum_confidence = minimum_confidence
        self.minimum_data_quality_score = minimum_data_quality_score
        self.max_target_weight = max_target_weight
        self.max_order_notional = max_order_notional

    def review(self, intent: TradeIntent) -> RiskReview:
        """Review a structured trade intent.

        Args:
            intent: Agent-generated trade intent.

        Returns:
            Risk review decision.
        """

        rejection_reasons: list[str] = []
        triggered_rules: list[str] = []
        if intent.confidence < self.minimum_confidence:
            rejection_reasons.append("confidence_below_threshold")
            triggered_rules.append("minimum_confidence")
        if intent.data_quality_score < self.minimum_data_quality_score:
            rejection_reasons.append("data_quality_below_threshold")
            triggered_rules.append("minimum_data_quality")
        if rejection_reasons:
            return RiskReview(
                review_id=uuid4(),
                decision_id=intent.decision_id,
                status="rejected",
                original_target_weight=intent.target_weight,
                approved_target_weight=Decimal("0"),
                max_order_notional=Decimal("0"),
                reasons=rejection_reasons,
                triggered_rules=triggered_rules,
                created_at_sim_time=intent.created_at_sim_time,
            )
        approved_target_weight = intent.target_weight
        status: Literal["approved", "resized"] = "approved"
        reasons: list[str] = []
        risk_rules: list[str] = []
        if abs(intent.target_weight) > self.max_target_weight:
            approved_target_weight = (
                self.max_target_weight
                if intent.target_weight > Decimal("0")
                else -self.max_target_weight
            )
            status = "resized"
            reasons.append("target_weight_exceeds_limit")
            risk_rules.append("max_target_weight")
        return RiskReview(
            review_id=uuid4(),
            decision_id=intent.decision_id,
            status=status,
            original_target_weight=intent.target_weight,
            approved_target_weight=approved_target_weight,
            max_order_notional=self.max_order_notional,
            reasons=reasons,
            triggered_rules=risk_rules,
            created_at_sim_time=intent.created_at_sim_time,
        )
