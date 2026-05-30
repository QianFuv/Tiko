"""Tests for read-only market data connector safety boundaries."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from tiko.data import (
    CRYPTOFEED_FORBIDDEN_CHANNELS,
    CRYPTOFEED_PUBLIC_CHANNELS,
    GuardedExchangeClient,
    MarketDataPermissionError,
    validate_cryptofeed_channels,
)


class FakeExchange:
    """Fake CCXT-style exchange that records method calls."""

    def __init__(self) -> None:
        """Initialize an empty call log."""

        self.calls: list[str] = []

    def fetchMarkets(self) -> list[dict[str, Any]]:
        """Return fake public market metadata.

        Returns:
            Fake market records.
        """

        self.calls.append("fetchMarkets")
        return [{"symbol": "BTC/USDT"}]

    def fetchTicker(self, symbol: str) -> dict[str, Any]:
        """Return a fake public ticker.

        Args:
            symbol: Symbol requested by the connector.

        Returns:
            Fake ticker data.
        """

        self.calls.append("fetchTicker")
        return {"symbol": symbol, "last": 100}

    def fetchTickers(self, symbols: list[str] | None = None) -> dict[str, Any]:
        """Return fake public tickers.

        Args:
            symbols: Optional requested symbols.

        Returns:
            Fake ticker mapping.
        """

        self.calls.append("fetchTickers")
        selected_symbols = symbols or ["BTC/USDT"]
        return {symbol: {"symbol": symbol, "last": 100} for symbol in selected_symbols}

    def fetchTrades(
        self, symbol: str, since: int | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return fake public trades.

        Args:
            symbol: Symbol requested by the connector.
            since: Optional start timestamp.
            limit: Optional maximum records.

        Returns:
            Fake trade records.
        """

        self.calls.append("fetchTrades")
        return [{"symbol": symbol, "since": since, "limit": limit}]

    def fetchOrderBook(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        """Return a fake public order book.

        Args:
            symbol: Symbol requested by the connector.
            limit: Optional book depth.

        Returns:
            Fake book data.
        """

        self.calls.append("fetchOrderBook")
        return {"symbol": symbol, "limit": limit, "bids": [], "asks": []}

    def fetchOHLCV(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[Any]]:
        """Return fake public OHLCV rows.

        Args:
            symbol: Symbol requested by the connector.
            timeframe: Requested candle timeframe.
            since: Optional start timestamp.
            limit: Optional maximum records.

        Returns:
            Fake OHLCV rows.
        """

        self.calls.append("fetchOHLCV")
        return [[0, 1, 2, 0.5, 1.5, 10, symbol, timeframe, since, limit]]

    def createOrder(self) -> None:
        """Fail if a private trading method is ever reached."""

        self.calls.append("createOrder")
        raise AssertionError("private method should not be called")


def test_public_market_data_methods_are_allowed() -> None:
    """Verify allowed public methods reach the exchange object."""

    exchange = FakeExchange()
    connector = GuardedExchangeClient(exchange)

    assert connector.fetch_markets() == [{"symbol": "BTC/USDT"}]
    assert connector.fetch_ticker("BTC/USDT")["last"] == 100
    assert connector.fetch_tickers(["ETH/USDT"])["ETH/USDT"]["last"] == 100
    assert connector.fetch_trades("BTC/USDT", limit=2)[0]["limit"] == 2
    assert connector.fetch_order_book("BTC/USDT", limit=5)["limit"] == 5
    assert connector.fetch_ohlcv("BTC/USDT", "1h", limit=1)[0][7] == "1h"
    assert exchange.calls == [
        "fetchMarkets",
        "fetchTicker",
        "fetchTickers",
        "fetchTrades",
        "fetchOrderBook",
        "fetchOHLCV",
    ]


def test_fetch_candles_normalizes_public_ohlcv_rows() -> None:
    """Verify guarded CCXT-style OHLCV rows normalize into candles."""

    exchange = FakeExchange()
    connector = GuardedExchangeClient(exchange, source_name="ccxt:test")

    candles = connector.fetch_candles(
        "BTC/USDT",
        "1h",
        limit=1,
        fetched_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
    )

    assert len(candles) == 1
    assert candles[0].symbol == "BTC/USDT"
    assert candles[0].close == Decimal("1.5")
    assert candles[0].source == "ccxt:test"
    assert candles[0].created_at == datetime(2026, 1, 1, 2, tzinfo=UTC)
    assert exchange.calls == ["fetchOHLCV"]


def test_private_method_is_blocked_before_exchange_call() -> None:
    """Verify private trading methods are blocked before the exchange sees them."""

    exchange = FakeExchange()
    connector = GuardedExchangeClient(exchange)

    with pytest.raises(MarketDataPermissionError):
        connector.call_method("createOrder")

    assert "createOrder" not in exchange.calls


def test_unknown_method_is_blocked() -> None:
    """Verify unsupported methods are blocked by default."""

    exchange = FakeExchange()
    connector = GuardedExchangeClient(exchange)

    with pytest.raises(MarketDataPermissionError):
        connector.call_method("fetchBalance")

    with pytest.raises(MarketDataPermissionError):
        connector.call_method("privateGetAccount")

    assert exchange.calls == []


def test_cryptofeed_channel_policy_allows_only_public_market_data() -> None:
    """Verify Cryptofeed channel policy excludes authenticated account channels."""

    assert validate_cryptofeed_channels(["trades", "ticker"]) == ("trades", "ticker")
    assert "trades" in CRYPTOFEED_PUBLIC_CHANNELS
    assert "orders" in CRYPTOFEED_FORBIDDEN_CHANNELS

    with pytest.raises(MarketDataPermissionError):
        validate_cryptofeed_channels(["orders"])

    with pytest.raises(MarketDataPermissionError):
        validate_cryptofeed_channels(["private_user_stream"])
