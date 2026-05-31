"""Local market data importers for normalized candle datasets."""

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pyarrow.parquet as parquet

from tiko.data.normalization import (
    REQUIRED_CANDLE_FIELDS,
    MarketDataNormalizationError,
    normalize_candle_record,
)
from tiko.data.validation import MarketDataValidationReport, MarketDataValidator
from tiko.domain.market import Candle


class MarketDataImportError(ValueError):
    """Raised when local market data import cannot proceed."""


@dataclass(frozen=True)
class CandleImportResult:
    """Return normalized candles and validation output for an import."""

    source_path: Path
    ingestion_run_id: UUID
    raw_records: tuple[dict[str, object], ...]
    candles: tuple[Candle, ...]
    validation_report: MarketDataValidationReport


class CsvCandleImporter:
    """Import candles from local CSV files."""

    def __init__(self, validator: MarketDataValidator | None = None) -> None:
        """Initialize the CSV importer.

        Args:
            validator: Optional market data validator.
        """

        self._validator = validator or MarketDataValidator()

    def import_file(self, path: str | Path) -> CandleImportResult:
        """Import and validate candles from a CSV file.

        Args:
            path: CSV file path.

        Returns:
            Candle import result.

        Raises:
            MarketDataImportError: If columns or rows cannot be imported.
        """

        source_path = Path(path)
        with source_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            self._validate_columns(reader.fieldnames)
            records = [dict(row) for row in reader]
        return self._import_records(source_path, records)

    def _validate_columns(self, fieldnames: Sequence[str] | None) -> None:
        """Validate CSV header columns.

        Args:
            fieldnames: CSV header field names.

        Raises:
            MarketDataImportError: If required columns are missing.
        """

        if fieldnames is None:
            raise MarketDataImportError("CSV file must include a header row.")
        validate_required_columns(fieldnames)

    def _import_records(
        self, source_path: Path, records: Iterable[Mapping[str, object]]
    ) -> CandleImportResult:
        """Normalize and validate raw records.

        Args:
            source_path: Import source path.
            records: Raw candle records.

        Returns:
            Candle import result.

        Raises:
            MarketDataImportError: If normalization fails.
        """

        ingestion_run_id = uuid4()
        raw_records = tuple(dict(record) for record in records)
        candles = normalize_records(
            raw_records,
            default_fetched_at=datetime.now(UTC),
            default_ingestion_run_id=ingestion_run_id,
        )
        return CandleImportResult(
            source_path=source_path,
            ingestion_run_id=ingestion_run_id,
            raw_records=raw_records,
            candles=tuple(candles),
            validation_report=self._validator.validate_candles(candles),
        )


class ParquetCandleImporter:
    """Import candles from local Parquet files."""

    def __init__(self, validator: MarketDataValidator | None = None) -> None:
        """Initialize the Parquet importer.

        Args:
            validator: Optional market data validator.
        """

        self._validator = validator or MarketDataValidator()

    def import_file(self, path: str | Path) -> CandleImportResult:
        """Import and validate candles from a Parquet file.

        Args:
            path: Parquet file path.

        Returns:
            Candle import result.

        Raises:
            MarketDataImportError: If columns or rows cannot be imported.
        """

        source_path = Path(path)
        table = parquet.read_table(source_path)
        validate_required_columns(table.column_names)
        ingestion_run_id = uuid4()
        raw_records = tuple(dict(record) for record in table.to_pylist())
        candles = normalize_records(
            raw_records,
            default_fetched_at=datetime.now(UTC),
            default_ingestion_run_id=ingestion_run_id,
        )
        return CandleImportResult(
            source_path=source_path,
            ingestion_run_id=ingestion_run_id,
            raw_records=raw_records,
            candles=tuple(candles),
            validation_report=self._validator.validate_candles(candles),
        )


def validate_required_columns(columns: Iterable[str]) -> None:
    """Validate required candle columns.

    Args:
        columns: Available column names.

    Raises:
        MarketDataImportError: If any required columns are missing.
    """

    missing_fields = REQUIRED_CANDLE_FIELDS.difference(columns)
    if missing_fields:
        missing_text = ", ".join(sorted(missing_fields))
        raise MarketDataImportError(
            f"Candle dataset is missing required columns: {missing_text}."
        )


def normalize_records(
    records: Iterable[Mapping[str, object]],
    default_fetched_at: datetime | None = None,
    default_ingestion_run_id: UUID | None = None,
) -> list[Candle]:
    """Normalize raw records into candle domain models.

    Args:
        records: Raw candle records.
        default_fetched_at: Fetched timestamp used when rows omit one.
        default_ingestion_run_id: Ingestion run ID used when rows omit one.

    Returns:
        Normalized candles.

    Raises:
        MarketDataImportError: If any record cannot be normalized.
    """

    candles: list[Candle] = []
    for index, record in enumerate(records):
        try:
            candles.append(
                normalize_candle_record(
                    record,
                    default_fetched_at=default_fetched_at,
                    default_ingestion_run_id=default_ingestion_run_id,
                )
            )
        except MarketDataNormalizationError as error:
            raise MarketDataImportError(
                f"Candle record at index {index} could not be normalized: {error}"
            ) from error
    return candles
