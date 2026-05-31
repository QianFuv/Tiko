"""Report routes for simulation review artifacts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from tiko.api.dependencies import get_simulation_service
from tiko.domain.reporting import ReportArtifact
from tiko.services import SimulationService

router = APIRouter(prefix="/reports", tags=["reports"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


@router.post("/simulations/{run_id}", response_model=ReportArtifact)
def create_simulation_report(
    run_id: UUID,
    service: SimulationServiceDep,
) -> ReportArtifact:
    """Create a structured simulation report.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Created report artifact.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.create_simulation_report(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/simulations/{run_id}", response_model=list[ReportArtifact])
def list_simulation_reports(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[ReportArtifact]:
    """List structured simulation reports.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Report artifacts.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_reports(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
