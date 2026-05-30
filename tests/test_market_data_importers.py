"""Tests for market data normalization, validation, and import."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tiko.data import (
    MarketDataValidator,
    normalize_candle_record,
    normalize_ccxt_ohlcv_row,
)
from tiko.domain.market import Candle


def test_normalize_candle_record_parses_scalars() -> None:
    """Verify raw mapping values normalize into a candle domain model."""

    candle = normalize_candle_record(
        {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2026-01-01T00:00:00Z",
            "close_time": "2026-01-01T01:00:00Z",
            "open": "100.10",
            "high": "110.50",
            "low": "90.25",
            "close": "105.75",
            "volume": "12.5",
            "quote_volume": "",
            "source": "csv",
            "as_of": "2026-01-01T01:00:00Z",
        }
    )

    assert candle.symbol == "BTCUSDT"
    assert candle.open == Decimal("100.10")
    assert candle.quote_volume is None
    assert candle.open_time == datetime(2026, 1, 1, tzinfo=UTC)
    assert candle.created_at == candle.as_of


def test_normalize_ccxt_ohlcv_row_uses_timeframe_close_time() -> None:
    """Verify public CCXT OHLCV rows normalize into point-in-time candles."""

    open_time = datetime(2026, 1, 1, tzinfo=UTC)
    timestamp_ms = int(open_time.timestamp() * 1000)

    candle = normalize_ccxt_ohlcv_row(
        row=[timestamp_ms, "100", "110", "95", "105", "2.5"],
        symbol="BTC/USDT",
        timeframe="1h",
        source="ccxt:binance",
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert candle.open_time == open_time
    assert candle.close_time == open_time + timedelta(hours=1)
    assert candle.as_of == candle.close_time
    assert candle.created_at == datetime(2026, 1, 2, tzinfo=UTC)


def test_validator_reports_price_and_availability_errors() -> None:
    """Verify validation reports semantic candle quality errors."""

    candle = Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=datetime(2026, 1, 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("99"),
        low=Decimal("101"),
        close=Decimal("100"),
        volume=Decimal("1"),
        quote_volume=None,
        source="test",
        as_of=datetime(2026, 1, 1, 0, 30, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )

    report = MarketDataValidator().validate_candles([candle])

    assert report.has_errors()
    assert report.error_count() == 3
    assert {issue.code for issue in report.issues} == {
        "as_of_before_close",
        "high_below_body",
        "low_above_body",
    }
