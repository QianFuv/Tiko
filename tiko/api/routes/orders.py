"""Simulated order and fill query routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

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


@router.get("/orders/{order_id}", response_model=SimOrder)
def get_order(
    order_id: UUID,
    service: SimulationServiceDep,
) -> SimOrder:
    """Get one simulated order.

    Args:
        order_id: Simulated order identifier.
        service: Simulation service dependency.

    Returns:
        Simulated order.

    Raises:
        HTTPException: If the order does not exist.
    """

    try:
        return service.get_order(order_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Order not found.") from error


@router.get("/fills", response_model=list[Fill])
def list_fills(service: SimulationServiceDep) -> list[Fill]:
    """List simulated fills across all runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Simulated fills.
    """

    return service.list_fills()


@router.get("/fills/{fill_id}", response_model=Fill)
def get_fill(
    fill_id: UUID,
    service: SimulationServiceDep,
) -> Fill:
    """Get one simulated fill.

    Args:
        fill_id: Simulated fill identifier.
        service: Simulation service dependency.

    Returns:
        Simulated fill.

    Raises:
        HTTPException: If the fill does not exist.
    """

    try:
        return service.get_fill(fill_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Fill not found.") from error
