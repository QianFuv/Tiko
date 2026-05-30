"""Simulated order and fill query routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from tiko.api.dependencies import get_simulation_service
from tiko.domain.order import Fill, SimOrder
from tiko.services import SimulationService

router = APIRouter(tags=["orders"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


@router.get("/orders", response_model=list[SimOrder])
def list_orders(service: SimulationServiceDep) -> list[SimOrder]:
    """List simulated orders across all runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Simulated orders.
    """

    return service.list_orders()


@router.get("/fills", response_model=list[Fill])
def list_fills(service: SimulationServiceDep) -> list[Fill]:
    """List simulated fills across all runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Simulated fills.
    """

    return service.list_fills()
