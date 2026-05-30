"""Slippage calculation for simulated execution."""

from decimal import Decimal
from typing import Literal

OrderSide = Literal["buy", "sell"]


class SlippageEngine:
    """Apply side-aware simulated market slippage."""

    def __init__(self, slippage_bps: Decimal = Decimal("2")) -> None:
        """Initialize slippage configuration.

        Args:
            slippage_bps: Slippage amount in basis points.
        """

        self.slippage_bps = slippage_bps

    def apply_market_slippage(
        self, reference_price: Decimal, side: OrderSide
    ) -> Decimal:
        """Apply market-order slippage to a reference price.

        Args:
            reference_price: Current market reference price.
            side: Order side.

        Returns:
            Slippage-adjusted fill price.
        """

        slippage_multiplier = self.slippage_bps / Decimal("10000")
        price_delta = reference_price * slippage_multiplier
        if side == "buy":
            return reference_price + price_delta
        return reference_price - price_delta
