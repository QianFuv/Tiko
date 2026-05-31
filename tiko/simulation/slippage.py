"""Slippage calculation for simulated execution."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class SlippageContext:
    """Represent market context for simulated market-order slippage."""

    volatility_bps: Decimal = Decimal("0")
    spread_bps: Decimal = Decimal("0")
    order_notional: Decimal = Decimal("0")
    depth_1pct_usd: Decimal | None = None


class SlippageEngine:
    """Apply side-aware simulated market slippage."""

    def __init__(
        self,
        slippage_bps: Decimal = Decimal("2"),
        volatility_multiplier: Decimal = Decimal("0.2"),
        liquidity_multiplier: Decimal = Decimal("1.5"),
    ) -> None:
        """Initialize slippage configuration.

        Args:
            slippage_bps: Base slippage amount in basis points.
            volatility_multiplier: Weight applied to volatility in basis points.
            liquidity_multiplier: Weight applied to order size versus market depth.
        """

        self.slippage_bps = slippage_bps
        self.volatility_multiplier = volatility_multiplier
        self.liquidity_multiplier = liquidity_multiplier

    def apply_market_slippage(
        self,
        reference_price: Decimal,
        side: OrderSide,
        context: SlippageContext | None = None,
    ) -> Decimal:
        """Apply market-order slippage to a reference price.

        Args:
            reference_price: Current market reference price.
            side: Order side.
            context: Optional market context for effective slippage.

        Returns:
            Slippage-adjusted fill price.
        """

        slippage_bps = self.calculate_market_slippage_bps(context)
        return self.apply_market_slippage_bps(reference_price, side, slippage_bps)

    def apply_market_slippage_bps(
        self,
        reference_price: Decimal,
        side: OrderSide,
        slippage_bps: Decimal,
    ) -> Decimal:
        """Apply a concrete slippage amount to a market reference price.

        Args:
            reference_price: Current market reference price.
            side: Order side.
            slippage_bps: Effective slippage in basis points.

        Returns:
            Slippage-adjusted fill price.
        """

        slippage_multiplier = slippage_bps / Decimal("10000")
        price_delta = reference_price * slippage_multiplier
        if side == "buy":
            return reference_price + price_delta
        return reference_price - price_delta

    def calculate_market_slippage_bps(
        self,
        context: SlippageContext | None = None,
    ) -> Decimal:
        """Calculate effective market-order slippage in basis points.

        Args:
            context: Optional market context for effective slippage.

        Returns:
            Effective slippage in basis points.
        """

        if context is None:
            return self.slippage_bps
        spread_impact = context.spread_bps / Decimal("2")
        volatility_impact = context.volatility_bps * self.volatility_multiplier
        liquidity_impact = self._calculate_liquidity_impact_bps(context)
        return self.slippage_bps + spread_impact + volatility_impact + liquidity_impact

    def _calculate_liquidity_impact_bps(self, context: SlippageContext) -> Decimal:
        """Calculate bps impact from order size relative to available depth.

        Args:
            context: Market context for effective slippage.

        Returns:
            Liquidity impact in basis points.
        """

        if (
            context.depth_1pct_usd is None
            or context.depth_1pct_usd <= Decimal("0")
            or context.order_notional <= Decimal("0")
        ):
            return Decimal("0")
        size_ratio = context.order_notional / context.depth_1pct_usd
        return size_ratio * self.liquidity_multiplier * Decimal("100")
