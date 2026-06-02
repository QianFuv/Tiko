"""Risk review service for structured trade intent."""

from decimal import Decimal
from typing import Literal
from uuid import uuid4

from tiko.domain.account import SimAccount
from tiko.domain.decision import TradeIntent
from tiko.domain.order import SimOrder
from tiko.domain.risk import RiskContext, RiskReview

ACTIVE_ORDER_STATUSES = frozenset({"submitted", "accepted", "open", "partially_filled"})


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
        max_gross_exposure: Decimal | None = None,
        max_net_exposure: Decimal | None = None,
        max_open_order_exposure: Decimal | None = None,
        max_spread_bps: Decimal | None = None,
        min_depth_1pct_usd: Decimal | None = None,
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
            max_gross_exposure: Optional gross exposure weight ceiling.
            max_net_exposure: Optional net exposure weight ceiling.
            max_open_order_exposure: Optional open-order exposure weight ceiling.
            max_spread_bps: Optional maximum orderbook spread.
            min_depth_1pct_usd: Optional minimum orderbook depth.

        Raises:
            ValueError: If numeric limits are invalid.
        """

        if max_leverage <= Decimal("0"):
            raise ValueError("max_leverage must be greater than zero.")
        optional_limits = {
            "max_gross_exposure": max_gross_exposure,
            "max_net_exposure": max_net_exposure,
            "max_open_order_exposure": max_open_order_exposure,
            "max_spread_bps": max_spread_bps,
            "min_depth_1pct_usd": min_depth_1pct_usd,
        }
        for name, value in optional_limits.items():
            if value is not None and value < Decimal("0"):
                raise ValueError(f"{name} must not be negative.")
        self.minimum_confidence = minimum_confidence
        self.minimum_data_quality_score = minimum_data_quality_score
        self.max_target_weight = max_target_weight
        self.max_order_notional = max_order_notional
        self.max_leverage = max_leverage
        self.max_drawdown = max_drawdown
        self.max_daily_loss = max_daily_loss
        self.allow_short = allow_short
        self.allow_leverage = allow_leverage
        self.max_gross_exposure = max_gross_exposure
        self.max_net_exposure = max_net_exposure
        self.max_open_order_exposure = max_open_order_exposure
        self.max_spread_bps = max_spread_bps
        self.min_depth_1pct_usd = min_depth_1pct_usd

    def review(
        self,
        intent: TradeIntent,
        account: SimAccount | None = None,
        context: RiskContext | None = None,
    ) -> RiskReview:
        """Review a structured trade intent.

        Args:
            intent: Agent-generated trade intent.
            account: Optional pre-trade simulated account state.
            context: Optional point-in-time portfolio and market context.

        Returns:
            Risk review decision.
        """

        circuit_reasons, circuit_rules = self._circuit_breaker_reasons(
            account,
            context,
        )
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
        context_reasons, context_rules = self._context_rejection_reasons(
            intent,
            account,
            context,
        )
        rejection_reasons.extend(context_reasons)
        triggered_rules.extend(context_rules)
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

    def _context_rejection_reasons(
        self,
        intent: TradeIntent,
        account: SimAccount | None,
        context: RiskContext | None,
    ) -> tuple[list[str], list[str]]:
        """Build rejection reasons from optional portfolio and market context.

        Args:
            intent: Agent-generated trade intent.
            account: Optional pre-trade account state.
            context: Optional point-in-time risk context.

        Returns:
            Reason codes and triggered rules.
        """

        if context is None:
            return [], []
        reasons: list[str] = []
        rules: list[str] = []
        if account is not None and account.total_equity > Decimal("0"):
            reasons, rules = self._exposure_rejection_reasons(
                intent,
                account,
                context,
            )
        liquidity_reasons, liquidity_rules = self._liquidity_rejection_reasons(context)
        reasons.extend(liquidity_reasons)
        rules.extend(liquidity_rules)
        return reasons, rules

    def _exposure_rejection_reasons(
        self,
        intent: TradeIntent,
        account: SimAccount,
        context: RiskContext,
    ) -> tuple[list[str], list[str]]:
        """Build exposure-related rejection reasons.

        Args:
            intent: Agent-generated trade intent.
            account: Pre-trade account state.
            context: Point-in-time risk context.

        Returns:
            Reason codes and triggered rules.
        """

        position_weights = self._position_weights(context, account)
        position_weights[intent.symbol] = intent.target_weight
        open_order_weight = self._open_order_weight(context.open_orders, account)
        open_order_gross = abs(open_order_weight)
        gross_exposure = (
            sum(abs(weight) for weight in position_weights.values()) + open_order_gross
        )
        net_exposure = abs(sum(position_weights.values()) + open_order_weight)
        checks = [
            (
                self.max_gross_exposure,
                gross_exposure,
                "gross_exposure_exceeds_limit",
                "max_gross_exposure",
            ),
            (
                self.max_net_exposure,
                net_exposure,
                "net_exposure_exceeds_limit",
                "max_net_exposure",
            ),
            (
                self.max_open_order_exposure,
                open_order_gross,
                "open_order_exposure_exceeds_limit",
                "max_open_order_exposure",
            ),
        ]
        reasons: list[str] = []
        rules: list[str] = []
        for limit, value, reason, rule in checks:
            if limit is not None and value > limit:
                reasons.append(reason)
                rules.append(rule)
        return reasons, rules

    def _liquidity_rejection_reasons(
        self, context: RiskContext
    ) -> tuple[list[str], list[str]]:
        """Build liquidity-related rejection reasons.

        Args:
            context: Point-in-time risk context.

        Returns:
            Reason codes and triggered rules.
        """

        if context.latest_orderbook is None:
            return [], []
        reasons: list[str] = []
        rules: list[str] = []
        if (
            self.max_spread_bps is not None
            and context.latest_orderbook.spread_bps > self.max_spread_bps
        ):
            reasons.append("spread_exceeds_limit")
            rules.append("max_spread_bps")
        if (
            self.min_depth_1pct_usd is not None
            and context.latest_orderbook.depth_1pct_usd < self.min_depth_1pct_usd
        ):
            reasons.append("depth_below_minimum")
            rules.append("min_depth_1pct_usd")
        return reasons, rules

    def _position_weights(
        self, context: RiskContext, account: SimAccount
    ) -> dict[str, Decimal]:
        """Calculate signed position weights by symbol.

        Args:
            context: Point-in-time risk context.
            account: Pre-trade account state.

        Returns:
            Signed weights keyed by symbol.
        """

        weights: dict[str, Decimal] = {}
        for position in context.positions:
            sign = Decimal("-1") if position.side == "short" else Decimal("1")
            weights[position.symbol] = (
                weights.get(position.symbol, Decimal("0"))
                + sign * position.notional / account.total_equity
            )
        return weights

    def _open_order_weight(
        self, orders: list[SimOrder], account: SimAccount
    ) -> Decimal:
        """Calculate signed active open-order weight.

        Args:
            orders: Candidate simulated orders.
            account: Pre-trade account state.

        Returns:
            Signed open-order exposure weight.
        """

        weight = Decimal("0")
        for order in orders:
            if order.status not in ACTIVE_ORDER_STATUSES or order.limit_price is None:
                continue
            sign = Decimal("1") if order.side == "buy" else Decimal("-1")
            weight += sign * order.quantity * order.limit_price / account.total_equity
        return weight

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
        self, account: SimAccount | None, context: RiskContext | None
    ) -> tuple[list[str], list[str]]:
        """Build account-state circuit breaker reasons.

        Args:
            account: Optional pre-trade simulated account state.
            context: Optional point-in-time risk context.

        Returns:
            Reason codes and triggered rule names.
        """

        if account is None or account.initial_equity <= Decimal("0"):
            return [], []
        reasons: list[str] = []
        rules: list[str] = []
        daily_realized_pnl = (
            context.daily_realized_pnl if context is not None else account.realized_pnl
        )
        daily_loss_ratio = self._loss_ratio(daily_realized_pnl, account)
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
