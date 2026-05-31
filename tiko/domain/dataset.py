"""Dataset schemas for research market data control-plane APIs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

DatasetSource = Literal["csv", "parquet", "public_api", "synthetic", "manual"]
DatasetStatus = Literal["validated", "invalid"]


class DatasetRecord(DomainModel):
    """Represent an imported market data dataset."""

    dataset_id: UUID
    name: str = Field(min_length=1)
    source: DatasetSource
    source_uri: str = Field(min_length=1)
    symbols: list[str]
    timeframes: list[str]
    candle_count: int = Field(ge=0)
    status: DatasetStatus
    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime


class DatasetQualityIssue(DomainModel):
    """Represent one dataset validation issue."""

    index: int = Field(ge=0)
    severity: Literal["error", "warning"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    open_time: str = Field(min_length=1)


class DatasetQualityReport(DomainModel):
    """Summarize validation quality for a dataset."""

    dataset_id: UUID
    total_records: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    has_errors: bool
    issues: list[DatasetQualityIssue] = Field(default_factory=list)
