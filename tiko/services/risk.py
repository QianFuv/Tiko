"""Risk review service for structured trade intent."""

from decimal import Decimal
from typing import Literal
from uuid import uuid4

from tiko.domain.account import SimAccount
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
        max_leverage: Decimal = Decimal("1"),
        max_drawdown: Decimal = Decimal("1"),
        max_daily_loss: Decimal = Decimal("1"),
        allow_short: bool = True,
        allow_leverage: bool = True,
    ) -> None:
        """Initialize risk thresholds.

        Args:
            minimum_confidence: Minimum confidence required to approve an intent.
            minimum_data_quality_score: Minimum data quality required.
            max_target_weight: Maximum absolute portfolio target weight.
            max_order_notional: Maximum simulated order notional.
            max_leverage: Maximum allowed leverage declared by the intent.
            max_drawdown: Maximum allowed drawdown ratio.
            max_daily_loss: Maximum allowed realized loss ratio.
            allow_short: Whether short exposure is allowed.
            allow_leverage: Whether leverage above 1x is allowed.

        Raises:
            ValueError: If max leverage is not positive.
        """

        if max_leverage <= Decimal("0"):
            raise ValueError("max_leverage must be greater than zero.")
        self.minimum_confidence = minimum_confidence
        self.minimum_data_quality_score = minimum_data_quality_score
        self.max_target_weight = max_target_weight
        self.max_order_notional = max_order_notional
        self.max_leverage = max_leverage
        self.max_drawdown = max_drawdown
        self.max_daily_loss = max_daily_loss
        self.allow_short = allow_short
        self.allow_leverage = allow_leverage

    def review(
        self, intent: TradeIntent, account: SimAccount | None = None
    ) -> RiskReview:
        """Review a structured trade intent.

        Args:
            intent: Agent-generated trade intent.
            account: Optional pre-trade simulated account state.

        Returns:
            Risk review decision.
        """

        circuit_reasons, circuit_rules = self._circuit_breaker_reasons(account)
        if circuit_reasons:
            return RiskReview(
                review_id=uuid4(),
                decision_id=intent.decision_id,
                status="circuit_blocked",
                original_target_weight=intent.target_weight,
                approved_target_weight=Decimal("0"),
                max_order_notional=Decimal("0"),
                reasons=circuit_reasons,
                triggered_rules=circuit_rules,
                created_at_sim_time=intent.created_at_sim_time,
            )
        rejection_reasons: list[str] = []
        triggered_rules: list[str] = []
        if intent.confidence < self.minimum_confidence:
            rejection_reasons.append("confidence_below_threshold")
            triggered_rules.append("minimum_confidence")
        if intent.data_quality_score < self.minimum_data_quality_score:
            rejection_reasons.append("data_quality_below_threshold")
            triggered_rules.append("minimum_data_quality")
        if not self.allow_short and self._requires_short_exposure(intent):
            rejection_reasons.append("short_exposure_not_allowed")
            triggered_rules.append("allow_short")
        if not self.allow_leverage and intent.max_leverage > Decimal("1"):
            rejection_reasons.append("leverage_not_allowed")
            triggered_rules.append("allow_leverage")
        if intent.max_leverage > self.max_leverage:
            rejection_reasons.append("leverage_exceeds_limit")
            triggered_rules.append("max_leverage")
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

    def _requires_short_exposure(self, intent: TradeIntent) -> bool:
        """Return whether an intent requests short exposure.

        Args:
            intent: Agent-generated trade intent.

        Returns:
            `True` when the intent opens, increases, or targets short exposure.
        """

        short_actions = {"open_short", "increase_short"}
        return intent.target_weight < Decimal("0") or intent.action in short_actions

    def _circuit_breaker_reasons(
        self, account: SimAccount | None
    ) -> tuple[list[str], list[str]]:
        """Build account-state circuit breaker reasons.

        Args:
            account: Optional pre-trade simulated account state.

        Returns:
            Reason codes and triggered rule names.
        """

        if account is None or account.initial_equity <= Decimal("0"):
            return [], []
        reasons: list[str] = []
        rules: list[str] = []
        daily_loss_ratio = self._loss_ratio(account.realized_pnl, account)
        if daily_loss_ratio >= self.max_daily_loss:
            reasons.append("daily_loss_limit_exceeded")
            rules.append("max_daily_loss")
        drawdown_ratio = self._drawdown_ratio(account.max_drawdown, account)
        if drawdown_ratio >= self.max_drawdown:
            reasons.append("drawdown_limit_exceeded")
            rules.append("max_drawdown")
        return reasons, rules

    def _loss_ratio(self, realized_pnl: Decimal, account: SimAccount) -> Decimal:
        """Return realized loss as a positive equity ratio.

        Args:
            realized_pnl: Current realized PnL.
            account: Simulated account state.

        Returns:
            Positive realized loss ratio.
        """

        if realized_pnl >= Decimal("0"):
            return Decimal("0")
        return abs(realized_pnl) / account.initial_equity

    def _drawdown_ratio(self, max_drawdown: Decimal, account: SimAccount) -> Decimal:
        """Return drawdown as a positive equity ratio.

        Args:
            max_drawdown: Account max drawdown ratio or amount.
            account: Simulated account state.

        Returns:
            Positive drawdown ratio.
        """

        absolute_drawdown = abs(max_drawdown)
        if absolute_drawdown <= Decimal("1"):
            return absolute_drawdown
        return absolute_drawdown / account.initial_equity
