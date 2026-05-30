"""Simulation lifecycle routes."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import get_simulation_service
from tiko.domain.simulation import SimulationRun
from tiko.services import SimulationService
from tiko.simulation.state import SimulationStepResult

router = APIRouter(prefix="/simulations", tags=["simulations"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


class SimulationCreateRequest(BaseModel):
    """Represent a request to create an in-memory simulation run."""

    name: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    start_sim_time: datetime | None = None


class SimulationStepRequest(BaseModel):
    """Represent a request to advance one simulation step."""

    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


@router.get("", response_model=list[SimulationRun])
def list_simulations(service: SimulationServiceDep) -> list[SimulationRun]:
    """List process-local simulation runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Simulation runs.
    """

    return service.list_runs()


@router.post("", response_model=SimulationRun)
def create_simulation(
    request: SimulationCreateRequest,
    service: SimulationServiceDep,
) -> SimulationRun:
    """Create an in-memory simulation run.

    Args:
        request: Simulation creation request.
        service: Simulation service dependency.

    Returns:
        Created simulation run.
    """

    return service.create_run(
        name=request.name,
        symbols=request.symbols,
        start_sim_time=request.start_sim_time,
    )


@router.get("/{run_id}", response_model=SimulationRun)
def get_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
) -> SimulationRun:
    """Get one simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Simulation run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.post("/{run_id}/step", response_model=SimulationStepResult)
def step_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
    request: SimulationStepRequest | None = None,
) -> SimulationStepResult:
    """Advance one simulation run by one step.

    Args:
        run_id: Simulation run identifier.
        request: Optional simulation step request.
        service: Simulation service dependency.

    Returns:
        Simulation step result.

    Raises:
        HTTPException: If the run does not exist.
    """

    confidence = request.confidence if request is not None else 0.7
    try:
        return service.step_run(run_id, confidence=confidence)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
