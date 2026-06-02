"""Read-only market data access boundaries for Tiko."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tiko.data.connectors import (
        ALLOWED_PUBLIC_METHODS,
        CRYPTOFEED_FORBIDDEN_CHANNELS,
        CRYPTOFEED_PUBLIC_CHANNELS,
        FORBIDDEN_PRIVATE_METHODS,
        CcxtReadOnlyConnector,
        GuardedExchangeClient,
        MarketDataPermissionError,
        ReadOnlyMarketDataConnector,
        validate_cryptofeed_channels,
    )
    from tiko.data.importers import (
        CandleImportResult,
        CsvCandleImporter,
        MarketDataImportError,
        ParquetCandleImporter,
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
        OrderBookValidationIssue,
        OrderBookValidationReport,
    )

EXPORT_MAP: dict[str, tuple[str, str]] = {
    "ALLOWED_PUBLIC_METHODS": ("tiko.data.connectors", "ALLOWED_PUBLIC_METHODS"),
    "CRYPTOFEED_FORBIDDEN_CHANNELS": (
        "tiko.data.connectors",
        "CRYPTOFEED_FORBIDDEN_CHANNELS",
    ),
    "CRYPTOFEED_PUBLIC_CHANNELS": (
        "tiko.data.connectors",
        "CRYPTOFEED_PUBLIC_CHANNELS",
    ),
    "FORBIDDEN_PRIVATE_METHODS": ("tiko.data.connectors", "FORBIDDEN_PRIVATE_METHODS"),
    "CcxtReadOnlyConnector": ("tiko.data.connectors", "CcxtReadOnlyConnector"),
    "CandleImportResult": ("tiko.data.importers", "CandleImportResult"),
    "CsvCandleImporter": ("tiko.data.importers", "CsvCandleImporter"),
    "GuardedExchangeClient": ("tiko.data.connectors", "GuardedExchangeClient"),
    "MarketDataImportError": ("tiko.data.importers", "MarketDataImportError"),
    "MarketDataNormalizationError": (
        "tiko.data.normalization",
        "MarketDataNormalizationError",
    ),
    "MarketDataPermissionError": (
        "tiko.data.connectors",
        "MarketDataPermissionError",
    ),
    "MarketDataValidationIssue": (
        "tiko.data.validation",
        "MarketDataValidationIssue",
    ),
    "MarketDataValidationReport": (
        "tiko.data.validation",
        "MarketDataValidationReport",
    ),
    "MarketDataValidator": ("tiko.data.validation", "MarketDataValidator"),
    "OrderBookValidationIssue": (
        "tiko.data.validation",
        "OrderBookValidationIssue",
    ),
    "OrderBookValidationReport": (
        "tiko.data.validation",
        "OrderBookValidationReport",
    ),
    "ParquetCandleImporter": ("tiko.data.importers", "ParquetCandleImporter"),
    "ReadOnlyMarketDataConnector": (
        "tiko.data.connectors",
        "ReadOnlyMarketDataConnector",
    ),
    "normalize_candle_record": ("tiko.data.normalization", "normalize_candle_record"),
    "normalize_ccxt_ohlcv_row": (
        "tiko.data.normalization",
        "normalize_ccxt_ohlcv_row",
    ),
    "validate_cryptofeed_channels": (
        "tiko.data.connectors",
        "validate_cryptofeed_channels",
    ),
}

__all__ = [
    "ALLOWED_PUBLIC_METHODS",
    "CRYPTOFEED_FORBIDDEN_CHANNELS",
    "CRYPTOFEED_PUBLIC_CHANNELS",
    "FORBIDDEN_PRIVATE_METHODS",
    "CcxtReadOnlyConnector",
    "CandleImportResult",
    "CsvCandleImporter",
    "GuardedExchangeClient",
    "MarketDataImportError",
    "MarketDataNormalizationError",
    "MarketDataPermissionError",
    "MarketDataValidationIssue",
    "MarketDataValidationReport",
    "MarketDataValidator",
    "OrderBookValidationIssue",
    "OrderBookValidationReport",
    "ParquetCandleImporter",
    "ReadOnlyMarketDataConnector",
    "normalize_candle_record",
    "normalize_ccxt_ohlcv_row",
    "validate_cryptofeed_channels",
]


def __getattr__(name: str) -> Any:
    """Resolve package exports without eager dependency imports.

    Args:
        name: Exported attribute name.

    Returns:
        Exported object from the owning module.

    Raises:
        AttributeError: If the name is not part of this package's public API.
    """

    try:
        module_name, export_name = EXPORT_MAP[name]
    except KeyError as error:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from error
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value
