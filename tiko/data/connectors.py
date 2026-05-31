"""Read-only market data connector contracts and guards."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import ccxt

from tiko.data.normalization import (
    MarketDataNormalizationError,
    normalize_ccxt_ohlcv_row,
)
from tiko.data.validation import MarketDataValidator
from tiko.domain.market import Candle

ALLOWED_PUBLIC_METHODS = frozenset(
    {
        "fetchMarkets",
        "fetchTicker",
        "fetchTickers",
        "fetchTrades",
        "fetchOrderBook",
        "fetchOHLCV",
    }
)

CRYPTOFEED_PUBLIC_CHANNELS = frozenset(
    {
        "trades",
        "l2_book",
        "ticker",
        "candles",
        "funding",
        "open_interest",
    }
)

CRYPTOFEED_FORBIDDEN_CHANNELS = frozenset(
    {
        "balances",
        "orders",
        "fills",
        "positions",
        "user_trades",
        "account",
    }
)

FORBIDDEN_PRIVATE_METHODS = frozenset(
    {
        "createOrder",
        "cancelOrder",
        "cancelAllOrders",
        "editOrder",
        "fetchBalance",
        "fetchOrder",
        "fetchOpenOrders",
        "fetchClosedOrders",
        "fetchMyTrades",
        "fetchPosition",
        "fetchPositions",
        "fetchLedger",
        "withdraw",
        "transfer",
    }
)


class MarketDataPermissionError(RuntimeError):
    """Raised when code attempts to access non-public market data behavior."""


class ReadOnlyMarketDataConnector(Protocol):
    """Define the public market data methods allowed by the architecture."""

    def fetch_markets(self) -> list[dict[str, Any]]:
        """Fetch public market metadata.

        Returns:
            Public market metadata records from a read-only source.
        """

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch a public ticker for one symbol.

        Args:
            symbol: Exchange symbol to query.

        Returns:
            Public ticker payload.
        """

    def fetch_tickers(self, symbols: Sequence[str] | None = None) -> dict[str, Any]:
        """Fetch public tickers for zero or more symbols.

        Args:
            symbols: Optional exchange symbols to query.

        Returns:
            Mapping of symbols to public ticker payloads.
        """

    def fetch_trades(
        self, symbol: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch recent public trades for one symbol.

        Args:
            symbol: Exchange symbol to query.
            limit: Optional maximum number of trades.

        Returns:
            Public trade payloads.
        """

    def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        """Fetch public order book depth for one symbol.

        Args:
            symbol: Exchange symbol to query.
            limit: Optional maximum depth.

        Returns:
            Public order book payload.
        """

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[Any]]:
        """Fetch public OHLCV candles for one symbol and timeframe.

        Args:
            symbol: Exchange symbol to query.
            timeframe: Candle timeframe.
            since: Optional start timestamp in milliseconds.
            limit: Optional maximum number of candles.

        Returns:
            Public OHLCV rows.
        """

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
        fetched_at: datetime | None = None,
        ingestion_run_id: UUID | None = None,
    ) -> list[Candle]:
        """Fetch normalized public candles for one symbol and timeframe.

        Args:
            symbol: Exchange symbol to query.
            timeframe: Candle timeframe.
            since: Optional start timestamp in milliseconds.
            limit: Optional maximum number of candles.
            fetched_at: Optional wall-clock fetch timestamp.
            ingestion_run_id: Optional ingestion run identifier.

        Returns:
            Normalized public candles.
        """


class GuardedExchangeClient:
    """Wrap an exchange object with a public market-data-only method guard."""

    def __init__(self, exchange: Any, source_name: str = "ccxt") -> None:
        """Initialize the guarded exchange wrapper.

        Args:
            exchange: Exchange-like object exposing CCXT-style public methods.
            source_name: Source label used for normalized market data.
        """

        self._exchange = exchange
        self._source_name = source_name

    def call_method(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a public market data method after enforcing safety policy.

        Args:
            method_name: CCXT-style method name to call.
            *args: Positional arguments for the exchange method.
            **kwargs: Keyword arguments for the exchange method.

        Returns:
            Exchange method result.

        Raises:
            MarketDataPermissionError: If the method is private or unsupported.
        """

        if (
            method_name in FORBIDDEN_PRIVATE_METHODS
            or method_name not in ALLOWED_PUBLIC_METHODS
        ):
            raise MarketDataPermissionError(
                f"Method {method_name} is not allowed for read-only market data."
            )
        method = getattr(self._exchange, method_name)
        return method(*args, **kwargs)

    def fetch_markets(self) -> list[dict[str, Any]]:
        """Fetch public market metadata.

        Returns:
            Public market metadata records.
        """

        return self.call_method("fetchMarkets")

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch a public ticker for one symbol.

        Args:
            symbol: Exchange symbol to query.

        Returns:
            Public ticker payload.
        """

        return self.call_method("fetchTicker", symbol)

    def fetch_tickers(self, symbols: Sequence[str] | None = None) -> dict[str, Any]:
        """Fetch public tickers for optional symbols.

        Args:
            symbols: Optional exchange symbols to query.

        Returns:
            Mapping of ticker payloads.
        """

        if symbols is None:
            return self.call_method("fetchTickers")
        return self.call_method("fetchTickers", list(symbols))

    def fetch_trades(
        self, symbol: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch recent public trades for one symbol.

        Args:
            symbol: Exchange symbol to query.
            limit: Optional maximum number of trades.

        Returns:
            Public trade payloads.
        """

        return self.call_method("fetchTrades", symbol, None, limit)

    def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        """Fetch public order book depth for one symbol.

        Args:
            symbol: Exchange symbol to query.
            limit: Optional maximum depth.

        Returns:
            Public order book payload.
        """

        return self.call_method("fetchOrderBook", symbol, limit)

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[Any]]:
        """Fetch public OHLCV candles for one symbol and timeframe.

        Args:
            symbol: Exchange symbol to query.
            timeframe: Candle timeframe.
            since: Optional start timestamp in milliseconds.
            limit: Optional maximum number of candles.

        Returns:
            Public OHLCV rows.
        """

        return self.call_method("fetchOHLCV", symbol, timeframe, since, limit)

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
        fetched_at: datetime | None = None,
        ingestion_run_id: UUID | None = None,
    ) -> list[Candle]:
        """Fetch and validate normalized public OHLCV candles.

        Args:
            symbol: Exchange symbol to query.
            timeframe: Candle timeframe.
            since: Optional start timestamp in milliseconds.
            limit: Optional maximum number of candles.
            fetched_at: Optional wall-clock fetch timestamp.
            ingestion_run_id: Optional ingestion run identifier.

        Returns:
            Normalized candles.

        Raises:
            MarketDataNormalizationError: If normalized candles fail validation.
        """

        candles = [
            normalize_ccxt_ohlcv_row(
                row=row,
                symbol=symbol,
                timeframe=timeframe,
                source=self._source_name,
                fetched_at=fetched_at,
                ingestion_run_id=ingestion_run_id,
            )
            for row in self.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        ]
        report = MarketDataValidator().validate_candles(candles)
        if report.has_errors():
            codes = ", ".join(issue.code for issue in report.issues)
            raise MarketDataNormalizationError(
                f"Fetched candle data failed validation: {codes}."
            )
        return candles


class CcxtReadOnlyConnector(GuardedExchangeClient):
    """Create a CCXT-backed read-only public market data connector."""

    def __init__(
        self, exchange_id: str, options: Mapping[str, Any] | None = None
    ) -> None:
        """Initialize a guarded CCXT exchange without trading credentials.

        Args:
            exchange_id: CCXT exchange identifier such as `binance`.
            options: Optional public exchange options.

        Raises:
            ValueError: If the exchange ID is not available in CCXT.
        """

        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Unknown CCXT exchange: {exchange_id}")
        exchange_class = getattr(ccxt, exchange_id)
        safe_options = dict(options or {})
        safe_options.pop("apiKey", None)
        safe_options.pop("secret", None)
        safe_options.pop("password", None)
        safe_options.setdefault("enableRateLimit", True)
        super().__init__(
            exchange_class(safe_options), source_name=f"ccxt:{exchange_id}"
        )


def validate_cryptofeed_channels(channels: Sequence[str]) -> tuple[str, ...]:
    """Validate that requested Cryptofeed channels are public market data only.

    Args:
        channels: Requested Cryptofeed channel names.

    Returns:
        Validated channel tuple.

    Raises:
        MarketDataPermissionError: If a channel is forbidden or unsupported.
    """

    requested_channels = tuple(channels)
    forbidden_channels = sorted(
        set(requested_channels).intersection(CRYPTOFEED_FORBIDDEN_CHANNELS)
    )
    if forbidden_channels:
        forbidden_text = ", ".join(forbidden_channels)
        raise MarketDataPermissionError(
            f"Cryptofeed channels are not allowed: {forbidden_text}."
        )
    unsupported_channels = sorted(
        set(requested_channels).difference(CRYPTOFEED_PUBLIC_CHANNELS)
    )
    if unsupported_channels:
        unsupported_text = ", ".join(unsupported_channels)
        raise MarketDataPermissionError(
            f"Cryptofeed channels are not recognized as public: {unsupported_text}."
        )
    return requested_channels
