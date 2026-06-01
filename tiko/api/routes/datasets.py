"""Dataset control-plane routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_dataset_service,
    require_permission,
)
from tiko.core.config import get_settings
from tiko.domain.dataset import DatasetQualityReport, DatasetRecord, DatasetSource
from tiko.domain.market import Candle
from tiko.domain.security import Principal
from tiko.services import AuditService, DatasetService, DatasetServiceError

router = APIRouter(prefix="/datasets", tags=["datasets"])
DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageDatasetPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_datasets"))
]


class DatasetUploadRequest(BaseModel):
    """Represent a server-local dataset upload request."""

    name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source: DatasetSource | None = None


@router.post("/upload", response_model=DatasetRecord)
def upload_dataset(
    request: DatasetUploadRequest,
    service: DatasetServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageDatasetPrincipalDep,
) -> DatasetRecord:
    """Import a server-local CSV or Parquet candle dataset.

    Args:
        request: Dataset upload request.
        service: Dataset service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Imported dataset record.

    Raises:
        HTTPException: If the dataset cannot be imported.
    """

    try:
        dataset = service.upload_dataset(
            name=request.name,
            source_path=request.source_path,
            source=request.source,
        )
    except DatasetServiceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit_service.record(
        principal=principal,
        action="dataset.upload",
        resource_type="dataset",
        resource_id=str(dataset.dataset_id),
        metadata={
            "name": dataset.name,
            "source": dataset.source,
            "candle_count": dataset.candle_count,
        },
    )
    return dataset


@router.post("/upload-file", response_model=DatasetRecord)
async def upload_dataset_file(
    name: Annotated[str, Form(min_length=1)],
    file: Annotated[UploadFile, File()],
    service: DatasetServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageDatasetPrincipalDep,
    source: Annotated[DatasetSource | None, Form()] = None,
) -> DatasetRecord:
    """Import a multipart CSV or Parquet candle dataset upload.

    Args:
        name: Dataset display name.
        file: Uploaded dataset file.
        service: Dataset service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.
        source: Optional explicit source type.

    Returns:
        Imported dataset record.

    Raises:
        HTTPException: If the dataset cannot be imported.
    """

    content = await file.read()
    try:
        dataset = service.upload_dataset_file(
            name=name,
            filename=file.filename or "",
            content=content,
            artifact_root=get_settings().artifact_root,
            source=source,
        )
    except DatasetServiceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit_service.record(
        principal=principal,
        action="dataset.upload",
        resource_type="dataset",
        resource_id=str(dataset.dataset_id),
        metadata={
            "name": dataset.name,
            "source": dataset.source,
            "source_uri": dataset.source_uri,
            "candle_count": dataset.candle_count,
        },
    )
    return dataset


@router.get("", response_model=list[DatasetRecord])
def list_datasets(service: DatasetServiceDep) -> list[DatasetRecord]:
    """List imported datasets.

    Args:
        service: Dataset service dependency.

    Returns:
        Imported dataset records.
    """

    return service.list_datasets()


@router.get("/{dataset_id}", response_model=DatasetRecord)
def get_dataset(
    dataset_id: UUID,
    service: DatasetServiceDep,
) -> DatasetRecord:
    """Get one imported dataset.

    Args:
        dataset_id: Dataset identifier.
        service: Dataset service dependency.

    Returns:
        Dataset record.

    Raises:
        HTTPException: If the dataset does not exist.
    """

    try:
        return service.get_dataset(dataset_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error


@router.post("/{dataset_id}/validate", response_model=DatasetQualityReport)
def validate_dataset(
    dataset_id: UUID,
    service: DatasetServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageDatasetPrincipalDep,
) -> DatasetQualityReport:
    """Recompute quality for one imported dataset.

    Args:
        dataset_id: Dataset identifier.
        service: Dataset service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated quality report.

    Raises:
        HTTPException: If the dataset does not exist.
    """

    try:
        report = service.validate_dataset(dataset_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
    audit_service.record(
        principal=principal,
        action="dataset.validate",
        resource_type="dataset",
        resource_id=str(dataset_id),
        metadata={
            "error_count": report.error_count,
            "warning_count": report.warning_count,
        },
    )
    return report


@router.get("/{dataset_id}/quality", response_model=DatasetQualityReport)
def get_dataset_quality(
    dataset_id: UUID,
    service: DatasetServiceDep,
) -> DatasetQualityReport:
    """Get the latest quality report for one dataset.

    Args:
        dataset_id: Dataset identifier.
        service: Dataset service dependency.

    Returns:
        Dataset quality report.

    Raises:
        HTTPException: If the dataset does not exist.
    """

    try:
        return service.get_quality_report(dataset_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error


@router.get("/{dataset_id}/candles", response_model=list[Candle])
def list_dataset_candles(
    dataset_id: UUID,
    service: DatasetServiceDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[Candle]:
    """List a bounded candle slice for one dataset.

    Args:
        dataset_id: Dataset identifier.
        service: Dataset service dependency.
        limit: Maximum candles to return.

    Returns:
        Candle slice.

    Raises:
        HTTPException: If the dataset does not exist.
    """

    try:
        return service.list_candles(dataset_id, limit=limit)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
