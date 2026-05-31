"""Tests for market data normalization, validation, and import."""

import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pyarrow as arrow
import pyarrow.parquet as parquet
import pytest

from tiko.data import (
    CsvCandleImporter,
    MarketDataImportError,
    MarketDataValidator,
    ParquetCandleImporter,
    normalize_candle_record,
    normalize_ccxt_ohlcv_row,
)
from tiko.domain.market import Candle, OrderBookSnapshot


def sample_candle_row() -> dict[str, str]:
    """Create a raw candle row used by file importer tests.

    Returns:
        Raw candle row with required fields.
    """

    return {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-01-01T01:00:00Z",
        "open": "100",
        "high": "110",
        "low": "90",
        "close": "105",
        "volume": "2.5",
        "quote_volume": "262.5",
        "source": "fixture",
        "as_of": "2026-01-01T01:00:00Z",
        "created_at": "2026-01-01T01:00:00Z",
    }


def validation_candle(
    symbol: str,
    timeframe: str,
    open_offset: timedelta,
    close_offset: timedelta,
) -> Candle:
    """Create a candle with explicit offsets for validator tests.

    Args:
        symbol: Candle symbol.
        timeframe: Candle timeframe.
        open_offset: Offset from the validation base time for open_time.
        close_offset: Offset from the validation base time for close_time.

    Returns:
        Candle domain model.
    """

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    open_time = base_time + open_offset
    close_time = base_time + close_offset
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("2.5"),
        quote_volume=None,
        source="validator-test",
        as_of=close_time,
        created_at=close_time,
    )


def validation_orderbook(
    as_of_offset: timedelta = timedelta(),
    sequence_number: int | None = None,
    checksum: str | None = None,
    expected_checksum: str | None = None,
    bids: list[tuple[Decimal, Decimal]] | None = None,
    asks: list[tuple[Decimal, Decimal]] | None = None,
) -> OrderBookSnapshot:
    """Create an order book snapshot for validator tests.

    Args:
        as_of_offset: Offset from the validation base time for as_of.
        sequence_number: Optional feed sequence number.
        checksum: Optional received checksum.
        expected_checksum: Optional expected checksum.
        bids: Optional bid levels.
        asks: Optional ask levels.

    Returns:
        Order book snapshot domain model.
    """

    return OrderBookSnapshot(
        symbol="BTCUSDT",
        as_of=datetime(2026, 1, 1, tzinfo=UTC) + as_of_offset,
        bids=bids if bids is not None else [(Decimal("99"), Decimal("1"))],
        asks=asks if asks is not None else [(Decimal("101"), Decimal("1"))],
        mid_price=Decimal("100"),
        spread_bps=Decimal("20"),
        depth_1pct_usd=Decimal("10000"),
        source="cryptofeed:test",
        sequence_number=sequence_number,
        checksum=checksum,
        expected_checksum=expected_checksum,
    )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write raw candle rows to a CSV fixture file.

    Args:
        path: Destination file path.
        rows: Raw rows to write.
    """

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_normalize_candle_record_parses_scalars() -> None:
    """Verify raw mapping values normalize into a candle domain model."""

    ingestion_run_id = uuid4()
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
            "fetched_at": "2026-01-01T01:05:00Z",
            "ingestion_run_id": str(ingestion_run_id),
        }
    )

    assert candle.symbol == "BTCUSDT"
    assert candle.open == Decimal("100.10")
    assert candle.quote_volume is None
    assert candle.open_time == datetime(2026, 1, 1, tzinfo=UTC)
    assert candle.fetched_at == datetime(2026, 1, 1, 1, 5, tzinfo=UTC)
    assert candle.ingestion_run_id == ingestion_run_id
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
    assert candle.fetched_at == datetime(2026, 1, 2, tzinfo=UTC)
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


def test_validator_reports_structural_time_series_issues() -> None:
    """Verify validation reports candle order, overlap, and gap issues."""

    report = MarketDataValidator().validate_candles(
        [
            validation_candle(
                "BTCUSDT",
                "1h",
                timedelta(hours=0),
                timedelta(hours=1),
            ),
            validation_candle(
                "BTCUSDT",
                "1h",
                timedelta(hours=3),
                timedelta(hours=4),
            ),
            validation_candle(
                "BTCUSDT",
                "1h",
                timedelta(hours=2),
                timedelta(hours=3),
            ),
            validation_candle(
                "ETHUSDT",
                "1h",
                timedelta(hours=0),
                timedelta(hours=1),
            ),
            validation_candle(
                "ETHUSDT",
                "1h",
                timedelta(minutes=30),
                timedelta(hours=1, minutes=30),
            ),
        ]
    )

    assert report.error_count() == 2
    assert {issue.code for issue in report.issues} == {
        "candle_gap",
        "out_of_order_candle",
        "overlapping_candle",
    }
    assert {issue.code for issue in report.issues if issue.severity == "warning"} == {
        "candle_gap"
    }


def test_validator_reports_timeframe_duration_issues() -> None:
    """Verify validation reports timeframe parsing and duration issues."""

    report = MarketDataValidator().validate_candles(
        [
            validation_candle(
                "BTCUSDT",
                "1h",
                timedelta(hours=0),
                timedelta(minutes=30),
            ),
            validation_candle(
                "ETHUSDT",
                "custom",
                timedelta(hours=0),
                timedelta(hours=1),
            ),
        ]
    )

    assert report.error_count() == 1
    assert {issue.code for issue in report.issues} == {
        "timeframe_duration_mismatch",
        "unknown_timeframe",
    }
    assert {issue.code for issue in report.issues if issue.severity == "warning"} == {
        "unknown_timeframe"
    }


def test_validator_reports_contextual_point_in_time_issues() -> None:
    """Verify validation reports run window and availability issues."""

    run_window_report = MarketDataValidator().validate_candles(
        [
            validation_candle(
                "BTCUSDT",
                "2h",
                timedelta(hours=0),
                timedelta(hours=2),
            )
        ],
        run_end=datetime(2026, 1, 1, 1, 30, tzinfo=UTC),
    )
    availability_report = MarketDataValidator().validate_candles(
        [
            validation_candle(
                "ETHUSDT",
                "1h",
                timedelta(hours=0),
                timedelta(hours=1),
            )
        ],
        availability_cutoff=datetime(2026, 1, 1, 0, 30, tzinfo=UTC),
    )

    assert run_window_report.error_count() == 1
    assert {issue.code for issue in run_window_report.issues} == {"future_candle"}
    assert availability_report.error_count() == 1
    assert {issue.code for issue in availability_report.issues} == {
        "future_availability"
    }


def test_validator_reports_orderbook_sequence_and_checksum_issues() -> None:
    """Verify order book validator reports feed sequence and checksum issues."""

    report = MarketDataValidator().validate_orderbooks(
        [
            validation_orderbook(
                sequence_number=1,
                checksum="expected",
                expected_checksum="expected",
            ),
            validation_orderbook(
                as_of_offset=timedelta(seconds=1),
                sequence_number=3,
                checksum="actual",
                expected_checksum="expected",
            ),
        ]
    )

    assert report.has_errors()
    assert report.error_count() == 1
    assert {issue.code for issue in report.issues} == {
        "orderbook_checksum_mismatch",
        "orderbook_sequence_gap",
    }
    assert {issue.code for issue in report.issues if issue.severity == "warning"} == {
        "orderbook_sequence_gap"
    }


def test_validator_reports_orderbook_structural_issues() -> None:
    """Verify order book validator reports crossed books and invalid levels."""

    report = MarketDataValidator().validate_orderbooks(
        [
            validation_orderbook(
                bids=[(Decimal("101"), Decimal("1"))],
                asks=[(Decimal("100"), Decimal("1"))],
            ),
            validation_orderbook(
                as_of_offset=timedelta(seconds=1),
                bids=[(Decimal("0"), Decimal("1"))],
                asks=[],
            ),
        ]
    )

    assert report.error_count() == 2
    assert {issue.code for issue in report.issues} == {
        "crossed_orderbook",
        "invalid_orderbook_level",
        "missing_orderbook_side",
    }
    assert {issue.code for issue in report.issues if issue.severity == "warning"} == {
        "missing_orderbook_side"
    }


def test_csv_importer_returns_candles_and_validation_report(tmp_path: Path) -> None:
    """Verify CSV import normalizes rows and returns validation output."""

    path = tmp_path / "candles.csv"
    write_csv(path, [sample_candle_row()])

    result = CsvCandleImporter().import_file(path)

    assert result.source_path == path
    assert result.raw_records == (sample_candle_row(),)
    assert len(result.candles) == 1
    assert result.candles[0].close == Decimal("105")
    assert result.candles[0].fetched_at is not None
    assert result.candles[0].ingestion_run_id == result.ingestion_run_id
    assert not result.validation_report.has_errors()


def test_parquet_importer_matches_csv_normalization(tmp_path: Path) -> None:
    """Verify Parquet import uses the same candle normalization path."""

    path = tmp_path / "candles.parquet"
    parquet.write_table(arrow.Table.from_pylist([sample_candle_row()]), path)

    result = ParquetCandleImporter().import_file(path)

    assert result.raw_records[0]["symbol"] == "BTCUSDT"
    assert len(result.candles) == 1
    assert result.candles[0].symbol == "BTCUSDT"
    assert result.candles[0].quote_volume == Decimal("262.5")
    assert result.candles[0].fetched_at is not None
    assert result.candles[0].ingestion_run_id == result.ingestion_run_id
    assert not result.validation_report.has_errors()


def test_csv_importer_rejects_missing_required_columns(tmp_path: Path) -> None:
    """Verify local imports fail loudly for incomplete candle schemas."""

    path = tmp_path / "missing.csv"
    write_csv(path, [{"symbol": "BTCUSDT"}])

    with pytest.raises(MarketDataImportError, match="missing required columns"):
        CsvCandleImporter().import_file(path)
