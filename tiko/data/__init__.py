"""Read-only market data access boundaries for Tiko."""

from tiko.data.connectors import (
    ALLOWED_PUBLIC_METHODS,
    FORBIDDEN_PRIVATE_METHODS,
    CcxtReadOnlyConnector,
    GuardedExchangeClient,
    MarketDataPermissionError,
    ReadOnlyMarketDataConnector,
)
from tiko.data.normalization import (
    MarketDataNormalizationError,
    normalize_candle_record,
    normalize_ccxt_ohlcv_row,
)
from tiko.data.validation import (
    MarketDataValidationIssue,
    MarketDataValidationReport,
    MarketDataValidator,
)

__all__ = [
    "ALLOWED_PUBLIC_METHODS",
    "FORBIDDEN_PRIVATE_METHODS",
    "CcxtReadOnlyConnector",
    "GuardedExchangeClient",
    "MarketDataNormalizationError",
    "MarketDataPermissionError",
    "MarketDataValidationIssue",
    "MarketDataValidationReport",
    "MarketDataValidator",
    "ReadOnlyMarketDataConnector",
    "normalize_candle_record",
    "normalize_ccxt_ohlcv_row",
]
