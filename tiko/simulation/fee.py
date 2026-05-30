"""Fee calculation for simulated execution."""

from decimal import Decimal


class FeeEngine:
    """Calculate simulated execution fees."""

    def __init__(self, fee_bps: Decimal = Decimal("5")) -> None:
        """Initialize fee configuration.

        Args:
            fee_bps: Fee rate in basis points.
        """

        self.fee_bps = fee_bps

    def calculate_fee(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Calculate fee for a simulated fill.

        Args:
            quantity: Filled quantity.
            price: Fill price.

        Returns:
            Fee amount in quote currency.
        """

        return quantity * price * self.fee_bps / Decimal("10000")
