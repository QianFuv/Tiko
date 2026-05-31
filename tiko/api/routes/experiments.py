"""Experiment control-plane routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_dataset_service,
    get_experiment_service,
    get_runtime_service,
    require_permission,
)
from tiko.domain.experiment import ExperimentKind, ExperimentRecord
from tiko.domain.security import Principal
from tiko.services import (
    AuditService,
    DatasetService,
    ExperimentService,
    RuntimeService,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])
ExperimentServiceDep = Annotated[ExperimentService, Depends(get_experiment_service)]
DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
RuntimeServiceDep = Annotated[RuntimeService, Depends(get_runtime_service)]
ManageExperimentPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_experiments"))
]


class ExperimentCreateRequest(BaseModel):
    """Represent a research experiment creation request."""

    name: str = Field(min_length=1)
    kind: ExperimentKind
    hypothesis: str = Field(min_length=1)
    dataset_id: UUID
    model_id: UUID | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


@router.post("", response_model=ExperimentRecord)
def create_experiment(
    request: ExperimentCreateRequest,
    service: ExperimentServiceDep,
    dataset_service: DatasetServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageExperimentPrincipalDep,
) -> ExperimentRecord:
    """Create a draft research experiment.

    Args:
        request: Experiment creation request.
        service: Experiment service dependency.
        dataset_service: Dataset service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created experiment record.

    Raises:
        HTTPException: If the referenced dataset does not exist.
    """

    try:
        dataset_service.get_dataset(request.dataset_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
    experiment = service.create_experiment(
        name=request.name,
        kind=request.kind,
        hypothesis=request.hypothesis,
        dataset_id=request.dataset_id,
        parameters=request.parameters,
        model_id=request.model_id,
    )
    audit_service.record(
        principal=principal,
        action="experiment.create",
        resource_type="experiment",
        resource_id=str(experiment.experiment_id),
        metadata={
            "name": experiment.name,
            "kind": experiment.kind,
            "dataset_id": str(experiment.dataset_id),
        },
    )
    return experiment


@router.get("", response_model=list[ExperimentRecord])
def list_experiments(service: ExperimentServiceDep) -> list[ExperimentRecord]:
    """List research experiments.

    Args:
        service: Experiment service dependency.

    Returns:
        Experiment records.
    """

    return service.list_experiments()


@router.get("/{experiment_id}", response_model=ExperimentRecord)
def get_experiment(
    experiment_id: UUID,
    service: ExperimentServiceDep,
) -> ExperimentRecord:
    """Get one research experiment.

    Args:
        experiment_id: Experiment identifier.
        service: Experiment service dependency.

    Returns:
        Experiment record.

    Raises:
        HTTPException: If the experiment does not exist.
    """

    try:
        return service.get_experiment(experiment_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Experiment not found.") from error


@router.post("/{experiment_id}/run", response_model=ExperimentRecord)
def queue_experiment_run(
    experiment_id: UUID,
    service: ExperimentServiceDep,
    runtime_service: RuntimeServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageExperimentPrincipalDep,
) -> ExperimentRecord:
    """Queue an experiment run without executing heavy work in the request.

    Args:
        experiment_id: Experiment identifier.
        service: Experiment service dependency.
        runtime_service: Runtime service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Queued experiment record.

    Raises:
        HTTPException: If the experiment does not exist.
    """

    try:
        source_experiment = service.get_experiment(experiment_id)
        job = runtime_service.create_job(
            job_type="experiment_run",
            resource_type="experiment",
            resource_id=str(experiment_id),
            payload={
                "dataset_id": str(source_experiment.dataset_id),
                "kind": source_experiment.kind,
            },
        )
        experiment = service.queue_run(experiment_id, job_id=job.job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Experiment not found.") from error
    audit_service.record(
        principal=principal,
        action="experiment.run.queue",
        resource_type="experiment",
        resource_id=str(experiment_id),
        metadata={"status": experiment.status, "job_id": str(job.job_id)},
    )
    return experiment
