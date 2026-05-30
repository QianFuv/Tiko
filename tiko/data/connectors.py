"""Read-only market data connector contracts and guards."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import ccxt

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


class GuardedExchangeClient:
    """Wrap an exchange object with a public market-data-only method guard."""

    def __init__(self, exchange: Any) -> None:
        """Initialize the guarded exchange wrapper.

        Args:
            exchange: Exchange-like object exposing CCXT-style public methods.
        """

        self._exchange = exchange

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
        super().__init__(exchange_class(safe_options))
