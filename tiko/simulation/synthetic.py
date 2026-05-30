"""Synthetic market data generation for deterministic simulation runs."""

from datetime import datetime, timedelta
from decimal import Decimal

from tiko.domain.market import Candle


def base_price_for_symbol(symbol: str) -> Decimal:
    """Return a deterministic base price for a symbol.

    Args:
        symbol: Market symbol.

    Returns:
        Base price used by the synthetic generator.
    """

    if symbol.startswith("ETH"):
        return Decimal("3000")
    if symbol.startswith("BTC"):
        return Decimal("50000")
    return Decimal("100")


def generate_synthetic_candle(
    symbol: str, step_index: int, close_time: datetime
) -> Candle:
    """Generate a deterministic synthetic candle for a simulation step.

    Args:
        symbol: Market symbol.
        step_index: Zero-based simulation step index.
        close_time: Candle close timestamp.

    Returns:
        Point-in-time synthetic candle.
    """

    base_price = base_price_for_symbol(symbol)
    step_offset = Decimal(step_index + 1) * Decimal("25")
    open_price = base_price + step_offset
    close_price = open_price + Decimal("10")
    high_price = close_price + Decimal("5")
    low_price = open_price - Decimal("5")
    volume = Decimal("100") + Decimal(step_index)
    return Candle(
        symbol=symbol,
        timeframe="1h",
        open_time=close_time - timedelta(hours=1),
        close_time=close_time,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        quote_volume=volume * close_price,
        source="synthetic",
        as_of=close_time,
        created_at=close_time,
    )
