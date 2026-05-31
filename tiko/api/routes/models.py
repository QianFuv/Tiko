"""Model registry routes for research artifacts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import get_model_registry_service
from tiko.domain.model import ModelRegistryEntry, ModelStatus, ModelType
from tiko.services import ModelRegistryService

router = APIRouter(prefix="/models", tags=["models"])
ModelRegistryServiceDep = Annotated[
    ModelRegistryService, Depends(get_model_registry_service)
]


class ModelRegisterRequest(BaseModel):
    """Represent a model registry creation request."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    model_type: ModelType
    algorithm: str = Field(min_length=1)
    training_dataset_id: UUID
    validation_dataset_id: UUID
    metrics: dict[str, object] = Field(default_factory=dict)
    artifact_uri: str = Field(min_length=1)
    status: ModelStatus = "draft"


class ModelStatusUpdateRequest(BaseModel):
    """Represent a model registry status update request."""

    status: ModelStatus


@router.get("", response_model=list[ModelRegistryEntry])
def list_models(service: ModelRegistryServiceDep) -> list[ModelRegistryEntry]:
    """List model registry entries.

    Args:
        service: Model registry service dependency.

    Returns:
        Registered model entries.
    """

    return service.list_models()


@router.post("", response_model=ModelRegistryEntry)
def register_model(
    request: ModelRegisterRequest,
    service: ModelRegistryServiceDep,
) -> ModelRegistryEntry:
    """Register a model artifact for simulated research use.

    Args:
        request: Model registration payload.
        service: Model registry service dependency.

    Returns:
        Registered model entry.
    """

    return service.register_model(
        name=request.name,
        version=request.version,
        model_type=request.model_type,
        algorithm=request.algorithm,
        training_dataset_id=request.training_dataset_id,
        validation_dataset_id=request.validation_dataset_id,
        metrics=request.metrics,
        artifact_uri=request.artifact_uri,
        status=request.status,
    )


@router.get("/{model_id}", response_model=ModelRegistryEntry)
def get_model(
    model_id: UUID,
    service: ModelRegistryServiceDep,
) -> ModelRegistryEntry:
    """Get one model registry entry.

    Args:
        model_id: Model identifier.
        service: Model registry service dependency.

    Returns:
        Model registry entry.

    Raises:
        HTTPException: If no model exists for the ID.
    """

    try:
        return service.get_model(model_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Model not found.") from error


@router.post("/{model_id}/status", response_model=ModelRegistryEntry)
def update_model_status(
    model_id: UUID,
    request: ModelStatusUpdateRequest,
    service: ModelRegistryServiceDep,
) -> ModelRegistryEntry:
    """Update one model registry status.

    Args:
        model_id: Model identifier.
        request: Status update payload.
        service: Model registry service dependency.

    Returns:
        Updated model registry entry.

    Raises:
        HTTPException: If no model exists for the ID.
    """

    try:
        return service.update_status(model_id, request.status)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Model not found.") from error
