"""Dataset registry service for imported research candles."""

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from tiko.data import (
    CsvCandleImporter,
    MarketDataImportError,
    MarketDataValidationReport,
    MarketDataValidator,
    ParquetCandleImporter,
)
from tiko.db.repositories import SimulationRepository
from tiko.domain.dataset import (
    DatasetQualityIssue,
    DatasetQualityReport,
    DatasetRecord,
    DatasetSource,
    DatasetStatus,
    RawMarketDataRecord,
)
from tiko.domain.market import Candle

DATASET_UPLOAD_URI_PREFIX = "artifact://datasets/uploads"


class DatasetServiceError(ValueError):
    """Raised when dataset service operations cannot proceed."""


class DatasetService:
    """Manage imported datasets with optional repository persistence."""

    def __init__(
        self,
        validator: MarketDataValidator | None = None,
        repository: SimulationRepository | None = None,
    ) -> None:
        """Initialize the dataset service.

        Args:
            validator: Optional market data validator.
            repository: Optional persistence repository.
        """

        self._validator = validator or MarketDataValidator()
        self._repository = repository
        self._csv_importer = CsvCandleImporter(self._validator)
        self._parquet_importer = ParquetCandleImporter(self._validator)
        self._datasets: dict[UUID, DatasetRecord] = {}
        self._candles: dict[UUID, tuple[Candle, ...]] = {}
        self._quality_reports: dict[UUID, DatasetQualityReport] = {}
        self._raw_records: dict[UUID, tuple[RawMarketDataRecord, ...]] = {}

    def upload_dataset(
        self,
        name: str,
        source_path: str,
        source: DatasetSource | None = None,
        source_uri: str | None = None,
    ) -> DatasetRecord:
        """Import a server-local candle dataset file.

        Args:
            name: Dataset display name.
            source_path: Server-local CSV or Parquet path.
            source: Optional explicit source type.
            source_uri: Optional lineage URI to store instead of the local path.

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
        record_source_uri = source_uri or str(result.source_path)
        record = self._build_dataset_record(
            dataset_id=dataset_id,
            name=name,
            source=resolved_source,
            source_uri=record_source_uri,
            candles=result.candles,
            status="invalid" if quality_report.has_errors else "validated",
        )
        raw_records = self._build_raw_records(
            dataset_id=dataset_id,
            source=resolved_source,
            source_uri=record_source_uri,
            ingestion_run_id=result.ingestion_run_id,
            raw_records=result.raw_records,
            candles=result.candles,
        )
        self._datasets[dataset_id] = record
        self._candles[dataset_id] = result.candles
        self._quality_reports[dataset_id] = quality_report
        self._raw_records[dataset_id] = raw_records
        if self._repository is not None:
            self._repository.save_dataset(
                record, result.candles, quality_report, raw_records=raw_records
            )
        return record

    def upload_dataset_file(
        self,
        name: str,
        filename: str,
        content: bytes,
        artifact_root: str | Path,
        source: DatasetSource | None = None,
    ) -> DatasetRecord:
        """Store and import an uploaded candle dataset file.

        Args:
            name: Dataset display name.
            filename: Original client-provided upload filename.
            content: Uploaded file bytes.
            artifact_root: Root directory for controlled local artifacts.
            source: Optional explicit source type.

        Returns:
            Imported dataset record.

        Raises:
            DatasetServiceError: If the upload cannot be stored or imported.
        """

        if not content:
            raise DatasetServiceError("Uploaded dataset file is empty.")

        safe_filename = self._safe_upload_filename(filename)
        inferred_source = self._source_from_path(Path(safe_filename))
        if source is not None and source != inferred_source:
            raise DatasetServiceError(
                "Uploaded dataset file extension does not match source."
            )

        upload_root = Path(artifact_root).resolve() / "datasets" / "uploads"
        stored_path = upload_root / f"{uuid4()}-{safe_filename}"
        digest = hashlib.sha256(content).hexdigest()
        try:
            upload_root.mkdir(parents=True, exist_ok=True)
            stored_path.write_bytes(content)
        except OSError as error:
            raise DatasetServiceError(str(error)) from error

        source_uri = f"{DATASET_UPLOAD_URI_PREFIX}/{stored_path.name}?sha256={digest}"
        return self.upload_dataset(
            name=name,
            source_path=str(stored_path),
            source=source or inferred_source,
            source_uri=source_uri,
        )

    def list_datasets(self) -> list[DatasetRecord]:
        """List imported datasets.

        Returns:
            Dataset records sorted by creation time.
        """

        if self._repository is not None:
            return self._repository.list_datasets()
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

        if self._repository is not None:
            dataset = self._repository.get_dataset(dataset_id)
            if dataset is None:
                raise KeyError(dataset_id)
            return dataset
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

        dataset = self.get_dataset(dataset_id)
        candles = self._get_candles_for_validation(dataset_id)
        validation_report = self._validator.validate_candles(candles)
        quality_report = self._build_quality_report(dataset_id, validation_report)
        status: DatasetStatus = "invalid" if quality_report.has_errors else "validated"
        updated_dataset = dataset.model_copy(update={"status": status})
        self._datasets[dataset_id] = updated_dataset
        self._quality_reports[dataset_id] = quality_report
        if self._repository is not None:
            self._repository.save_dataset(updated_dataset, candles, quality_report)
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

        if self._repository is not None:
            report = self._repository.get_dataset_quality_report(dataset_id)
            if report is None:
                raise KeyError(dataset_id)
            return report
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

        if self._repository is not None:
            self.get_dataset(dataset_id)
            return self._repository.list_dataset_candles(dataset_id, limit)
        return list(self._candles[dataset_id][:limit])

    def list_raw_records(self, dataset_id: UUID) -> list[RawMarketDataRecord]:
        """List raw market data rows captured for a dataset.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Raw market data records ordered by row index.

        Raises:
            KeyError: If the dataset does not exist.
        """

        if self._repository is not None:
            self.get_dataset(dataset_id)
            return self._repository.list_raw_market_data_records(dataset_id)
        return list(self._raw_records[dataset_id])

    def _get_candles_for_validation(self, dataset_id: UUID) -> tuple[Candle, ...]:
        """Load candles for dataset validation.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset candles.

        Raises:
            KeyError: If the dataset does not exist.
        """

        if self._repository is not None:
            return tuple(self._repository.list_dataset_candles(dataset_id))
        return self._candles[dataset_id]

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

    def _safe_upload_filename(self, filename: str) -> str:
        """Validate a dataset upload filename for controlled storage.

        Args:
            filename: Original client-provided upload filename.

        Returns:
            Safe filename that can be combined with a generated prefix.

        Raises:
            DatasetServiceError: If the filename is empty or includes path segments.
        """

        safe_filename = filename.strip()
        if not safe_filename:
            raise DatasetServiceError("Uploaded dataset file name is required.")
        if "/" in safe_filename or "\\" in safe_filename:
            raise DatasetServiceError(
                "Uploaded dataset file name must not include path separators."
            )
        if safe_filename in {".", ".."}:
            raise DatasetServiceError("Uploaded dataset file name is invalid.")
        return safe_filename

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

    def _build_raw_records(
        self,
        dataset_id: UUID,
        source: DatasetSource,
        source_uri: str,
        ingestion_run_id: UUID,
        raw_records: tuple[dict[str, object], ...],
        candles: tuple[Candle, ...],
    ) -> tuple[RawMarketDataRecord, ...]:
        """Build raw market data records for durable replay and audit.

        Args:
            dataset_id: Dataset identifier.
            source: Dataset source type.
            source_uri: Source URI or path.
            ingestion_run_id: Import run identifier shared by normalized candles.
            raw_records: Raw row payloads from the importer.
            candles: Normalized candles created from the raw rows.

        Returns:
            Raw market data records ordered by row index.
        """

        created_at = datetime.now(UTC)
        return tuple(
            RawMarketDataRecord(
                raw_record_id=uuid5(
                    NAMESPACE_URL, f"raw-market-data:{dataset_id}:{row_index}"
                ),
                dataset_id=dataset_id,
                ingestion_run_id=ingestion_run_id,
                source=source,
                source_uri=source_uri,
                row_index=row_index,
                payload=self._normalize_raw_payload(payload),
                fetched_at=candles[row_index].fetched_at
                if row_index < len(candles)
                else None,
                created_at=created_at,
            )
            for row_index, payload in enumerate(raw_records)
        )

    def _normalize_raw_payload(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Convert raw payload values into JSON-compatible values.

        Args:
            payload: Raw importer payload.

        Returns:
            JSON-compatible payload dictionary.
        """

        return {
            str(key): self._normalize_raw_payload_value(value)
            for key, value in payload.items()
        }

    def _normalize_raw_payload_value(self, value: object) -> object:
        """Convert one raw payload value into a JSON-compatible value.

        Args:
            value: Raw payload value.

        Returns:
            JSON-compatible value.
        """

        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal | UUID | Path):
            return str(value)
        if isinstance(value, Mapping):
            return {
                str(key): self._normalize_raw_payload_value(nested_value)
                for key, nested_value in value.items()
            }
        if isinstance(value, list | tuple):
            return [self._normalize_raw_payload_value(item) for item in value]
        return str(value)
