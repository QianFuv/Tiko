"""Run benchmark and comparison routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tiko.api.dependencies import (
    get_audit_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.comparison import RunBenchmark, RunComparison
from tiko.domain.security import Principal
from tiko.services import AuditService, SimulationService

router = APIRouter(prefix="/comparisons", tags=["comparisons"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageResearchPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_research"))
]


class RunComparisonRequest(BaseModel):
    """Represent a pairwise run comparison request."""

    baseline_run_id: UUID
    candidate_run_id: UUID


@router.get("/runs/{run_id}/benchmark", response_model=RunBenchmark)
def get_run_benchmark(
    run_id: UUID,
    service: SimulationServiceDep,
) -> RunBenchmark:
    """Build a deterministic benchmark for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Run benchmark summary.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.build_benchmark(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.post("/runs", response_model=RunComparison)
def compare_runs(
    request: RunComparisonRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> RunComparison:
    """Compare two simulation runs.

    Args:
        request: Run comparison request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Pairwise run comparison.

    Raises:
        HTTPException: If either run does not exist.
    """

    try:
        comparison = service.compare_runs(
            baseline_run_id=request.baseline_run_id,
            candidate_run_id=request.candidate_run_id,
        )
        audit_service.record(
            principal=principal,
            action="comparison.run.create",
            resource_type="run_comparison",
            resource_id=f"{request.baseline_run_id}:{request.candidate_run_id}",
            metadata={
                "baseline_run_id": str(request.baseline_run_id),
                "candidate_run_id": str(request.candidate_run_id),
            },
        )
        return comparison
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
