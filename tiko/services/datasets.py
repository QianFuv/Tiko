"""Dataset registry service for imported research candles."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from tiko.data import (
    CsvCandleImporter,
    MarketDataImportError,
    MarketDataValidationReport,
    MarketDataValidator,
    ParquetCandleImporter,
)
from tiko.domain.dataset import (
    DatasetQualityIssue,
    DatasetQualityReport,
    DatasetRecord,
    DatasetSource,
    DatasetStatus,
)
from tiko.domain.market import Candle


class DatasetServiceError(ValueError):
    """Raised when dataset service operations cannot proceed."""


class DatasetService:
    """Manage process-local imported datasets."""

    def __init__(self, validator: MarketDataValidator | None = None) -> None:
        """Initialize the dataset service.

        Args:
            validator: Optional market data validator.
        """

        self._validator = validator or MarketDataValidator()
        self._csv_importer = CsvCandleImporter(self._validator)
        self._parquet_importer = ParquetCandleImporter(self._validator)
        self._datasets: dict[UUID, DatasetRecord] = {}
        self._candles: dict[UUID, tuple[Candle, ...]] = {}
        self._quality_reports: dict[UUID, DatasetQualityReport] = {}

    def upload_dataset(
        self,
        name: str,
        source_path: str,
        source: DatasetSource | None = None,
    ) -> DatasetRecord:
        """Import a server-local candle dataset file.

        Args:
            name: Dataset display name.
            source_path: Server-local CSV or Parquet path.
            source: Optional explicit source type.

        Returns:
            Imported dataset record.

        Raises:
            DatasetServiceError: If the source type is unsupported or import fails.
        """

        path = Path(source_path)
        resolved_source = source or self._source_from_path(path)
        try:
            if resolved_source == "csv":
                result = self._csv_importer.import_file(path)
            elif resolved_source == "parquet":
                result = self._parquet_importer.import_file(path)
            else:
                raise DatasetServiceError(
                    "Only CSV and Parquet dataset uploads are supported."
                )
        except (OSError, MarketDataImportError) as error:
            raise DatasetServiceError(str(error)) from error

        dataset_id = uuid4()
        quality_report = self._build_quality_report(
            dataset_id, result.validation_report
        )
        record = self._build_dataset_record(
            dataset_id=dataset_id,
            name=name,
            source=resolved_source,
            source_uri=str(result.source_path),
            candles=result.candles,
            status="invalid" if quality_report.has_errors else "validated",
        )
        self._datasets[dataset_id] = record
        self._candles[dataset_id] = result.candles
        self._quality_reports[dataset_id] = quality_report
        return record

    def list_datasets(self) -> list[DatasetRecord]:
        """List imported datasets.

        Returns:
            Dataset records sorted by creation time.
        """

        return sorted(self._datasets.values(), key=lambda dataset: dataset.created_at)

    def get_dataset(self, dataset_id: UUID) -> DatasetRecord:
        """Get one imported dataset.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset record.

        Raises:
            KeyError: If the dataset does not exist.
        """

        return self._datasets[dataset_id]

    def validate_dataset(self, dataset_id: UUID) -> DatasetQualityReport:
        """Recompute dataset quality and update dataset status.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Updated quality report.

        Raises:
            KeyError: If the dataset does not exist.
        """

        candles = self._candles[dataset_id]
        validation_report = self._validator.validate_candles(candles)
        quality_report = self._build_quality_report(dataset_id, validation_report)
        dataset = self._datasets[dataset_id]
        status: DatasetStatus = "invalid" if quality_report.has_errors else "validated"
        self._datasets[dataset_id] = dataset.model_copy(update={"status": status})
        self._quality_reports[dataset_id] = quality_report
        return quality_report

    def get_quality_report(self, dataset_id: UUID) -> DatasetQualityReport:
        """Get the latest quality report for a dataset.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset quality report.

        Raises:
            KeyError: If the dataset does not exist.
        """

        return self._quality_reports[dataset_id]

    def list_candles(self, dataset_id: UUID, limit: int) -> list[Candle]:
        """List a limited candle slice for a dataset.

        Args:
            dataset_id: Dataset identifier.
            limit: Maximum candles to return.

        Returns:
            Candle slice.

        Raises:
            KeyError: If the dataset does not exist.
        """

        return list(self._candles[dataset_id][:limit])

    def _source_from_path(self, path: Path) -> DatasetSource:
        """Resolve a dataset source from a file extension.

        Args:
            path: Dataset file path.

        Returns:
            Dataset source.

        Raises:
            DatasetServiceError: If the extension is unsupported.
        """

        suffix = path.suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix in {".parquet", ".pq"}:
            return "parquet"
        raise DatasetServiceError(
            "Dataset source_path must end with .csv, .parquet, or .pq."
        )

    def _build_dataset_record(
        self,
        dataset_id: UUID,
        name: str,
        source: DatasetSource,
        source_uri: str,
        candles: tuple[Candle, ...],
        status: DatasetStatus,
    ) -> DatasetRecord:
        """Build a dataset record from imported candles.

        Args:
            dataset_id: Dataset identifier.
            name: Dataset display name.
            source: Dataset source type.
            source_uri: Source URI or path.
            candles: Imported candles.
            status: Dataset validation status.

        Returns:
            Dataset record.
        """

        return DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            source=source,
            source_uri=source_uri,
            symbols=sorted({candle.symbol for candle in candles}),
            timeframes=sorted({candle.timeframe for candle in candles}),
            candle_count=len(candles),
            status=status,
            start_time=min((candle.open_time for candle in candles), default=None),
            end_time=max((candle.close_time for candle in candles), default=None),
            created_at=datetime.now(UTC),
        )

    def _build_quality_report(
        self,
        dataset_id: UUID,
        validation_report: MarketDataValidationReport,
    ) -> DatasetQualityReport:
        """Convert validator output into an API quality report.

        Args:
            dataset_id: Dataset identifier.
            validation_report: Raw market data validation report.

        Returns:
            Dataset quality report.
        """

        issues = [
            DatasetQualityIssue(
                index=issue.index,
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                symbol=issue.symbol,
                open_time=issue.open_time,
            )
            for issue in validation_report.issues
        ]
        warning_count = sum(1 for issue in issues if issue.severity == "warning")
        return DatasetQualityReport(
            dataset_id=dataset_id,
            total_records=validation_report.total_records,
            error_count=validation_report.error_count(),
            warning_count=warning_count,
            has_errors=validation_report.has_errors(),
            issues=issues,
        )
