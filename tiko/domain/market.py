"""Market data and event schemas for point-in-time simulation input."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel


class Asset(DomainModel):
    """Describe a tradable or synthetic market instrument."""

    symbol: str = Field(min_length=1)
    base_asset: str = Field(min_length=1)
    quote_asset: str = Field(min_length=1)
    market_type: Literal["spot", "perp", "synthetic"]
    tick_size: Decimal = Field(gt=Decimal("0"))
    lot_size: Decimal = Field(gt=Decimal("0"))
    min_notional: Decimal = Field(ge=Decimal("0"))
    fee_tier: str = Field(min_length=1)
    is_active: bool


class Candle(DomainModel):
    """Represent one OHLCV candle with point-in-time availability metadata."""

    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    open_time: datetime
    close_time: datetime
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: Decimal = Field(ge=Decimal("0"))
    quote_volume: Decimal | None = Field(default=None, ge=Decimal("0"))
    source: str = Field(min_length=1)
    as_of: datetime
    fetched_at: datetime | None = None
    ingestion_run_id: UUID | None = None
    created_at: datetime


class OrderBookSnapshot(DomainModel):
    """Represent a normalized order book snapshot from a read-only source."""

    symbol: str = Field(min_length=1)
    as_of: datetime
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    mid_price: Decimal = Field(gt=Decimal("0"))
    spread_bps: Decimal = Field(ge=Decimal("0"))
    depth_1pct_usd: Decimal = Field(ge=Decimal("0"))
    source: str = Field(min_length=1)
    sequence_number: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, min_length=1)
    expected_checksum: str | None = Field(default=None, min_length=1)


class FeatureSnapshot(DomainModel):
    """Represent derived point-in-time market features."""

    snapshot_id: UUID
    run_id: UUID
    symbol: str = Field(min_length=1)
    as_of: datetime
    features: dict[str, object]
    source: str = Field(min_length=1)


class MarketEvent(DomainModel):
    """Represent a simulation event emitted from market data or synthetic input."""

    event_id: UUID
    type: Literal[
        "candle_closed",
        "tick",
        "orderbook_snapshot",
        "funding_update",
        "news_event",
        "liquidity_shock",
        "volatility_shock",
        "system_event",
    ]
    symbol: str | None
    simulated_time: datetime
    payload: dict[str, object]
    source: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
