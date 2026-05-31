"""Run benchmark and comparison routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tiko.api.dependencies import get_simulation_service
from tiko.domain.comparison import RunBenchmark, RunComparison
from tiko.services import SimulationService

router = APIRouter(prefix="/comparisons", tags=["comparisons"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


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
) -> RunComparison:
    """Compare two simulation runs.

    Args:
        request: Run comparison request.
        service: Simulation service dependency.

    Returns:
        Pairwise run comparison.

    Raises:
        HTTPException: If either run does not exist.
    """

    try:
        return service.compare_runs(
            baseline_run_id=request.baseline_run_id,
            candidate_run_id=request.candidate_run_id,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
