"""Model registry routes for research artifacts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_model_registry_service,
    require_permission,
)
from tiko.domain.model import ModelRegistryEntry, ModelStatus, ModelType
from tiko.domain.rl import RlPolicySignal
from tiko.domain.security import Principal
from tiko.services import AuditService, ModelRegistryService

router = APIRouter(prefix="/models", tags=["models"])
ModelRegistryServiceDep = Annotated[
    ModelRegistryService, Depends(get_model_registry_service)
]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageResearchPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_research"))
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
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> ModelRegistryEntry:
    """Register a model artifact for simulated research use.

    Args:
        request: Model registration payload.
        service: Model registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Registered model entry.
    """

    entry = service.register_model(
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
    audit_service.record(
        principal=principal,
        action="model.register",
        resource_type="model",
        resource_id=str(entry.model_id),
        metadata={"name": entry.name, "version": entry.version},
    )
    return entry


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
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> ModelRegistryEntry:
    """Update one model registry status.

    Args:
        model_id: Model identifier.
        request: Status update payload.
        service: Model registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated model registry entry.

    Raises:
        HTTPException: If no model exists for the ID.
    """

    try:
        entry = service.update_status(model_id, request.status)
        audit_service.record(
            principal=principal,
            action="model.status.update",
            resource_type="model",
            resource_id=str(model_id),
            metadata={"status": entry.status},
        )
        return entry
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Model not found.") from error


@router.post("/{model_id}/promote", response_model=ModelRegistryEntry)
def promote_model(
    model_id: UUID,
    service: ModelRegistryServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> ModelRegistryEntry:
    """Promote one model to simulated paper-enabled status.

    Args:
        model_id: Model identifier.
        service: Model registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Promoted model registry entry.

    Raises:
        HTTPException: If no model exists for the ID.
    """

    try:
        entry = service.promote_model(model_id)
        audit_service.record(
            principal=principal,
            action="model.promote",
            resource_type="model",
            resource_id=str(model_id),
            metadata={"status": entry.status},
        )
        return entry
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Model not found.") from error


@router.post("/{model_id}/policy-signal", response_model=RlPolicySignal)
def serve_model_policy_signal(
    model_id: UUID,
    service: ModelRegistryServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> RlPolicySignal:
    """Serve an advisory policy signal from one model.

    Args:
        model_id: Model identifier.
        service: Model registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Advisory RL policy signal.

    Raises:
        HTTPException: If no model exists or serving is not allowed.
    """

    try:
        signal = service.serve_policy_signal(model_id)
        audit_service.record(
            principal=principal,
            action="model.policy_signal.serve",
            resource_type="model",
            resource_id=str(model_id),
            metadata={
                "action_id": signal.action_id,
                "target_weight": str(signal.target_weight),
            },
        )
        return signal
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Model not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{model_id}/archive", response_model=ModelRegistryEntry)
def archive_model(
    model_id: UUID,
    service: ModelRegistryServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> ModelRegistryEntry:
    """Archive one model registry entry.

    Args:
        model_id: Model identifier.
        service: Model registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Archived model registry entry.

    Raises:
        HTTPException: If no model exists for the ID.
    """

    try:
        entry = service.archive_model(model_id)
        audit_service.record(
            principal=principal,
            action="model.archive",
            resource_type="model",
            resource_id=str(model_id),
            metadata={"status": entry.status},
        )
        return entry
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Model not found.") from error
