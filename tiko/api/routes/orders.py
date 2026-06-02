"""Simulated order and fill query routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import get_simulation_service, require_permission
from tiko.domain.order import Fill, SimOrder
from tiko.domain.security import Principal
from tiko.services import SimulationService

router = APIRouter(tags=["orders"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
ManageSimulationPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_simulations"))
]


class CancelAllOrdersRequest(BaseModel):
    """Represent a request to cancel active orders for one run."""

    run_id: UUID
    symbol: str | None = Field(default=None, min_length=1)


@router.get("/orders", response_model=list[SimOrder])
def list_orders(service: SimulationServiceDep) -> list[SimOrder]:
    """List simulated orders across all runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Simulated orders.
    """

    return service.list_orders()


@router.post("/orders/cancel-all", response_model=list[SimOrder])
def cancel_all_orders(
    request: CancelAllOrdersRequest,
    service: SimulationServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> list[SimOrder]:
    """Cancel active simulated orders for one run.

    Args:
        request: Cancel-all request.
        service: Simulation service dependency.
        principal: Authorized caller principal.

    Returns:
        Canceled orders.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return list(service.cancel_all_orders(request.run_id, symbol=request.symbol))
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


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


@router.post("/orders/{order_id}/cancel", response_model=SimOrder)
def cancel_order(
    order_id: UUID,
    service: SimulationServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimOrder:
    """Cancel one active simulated order.

    Args:
        order_id: Simulated order identifier.
        service: Simulation service dependency.
        principal: Authorized caller principal.

    Returns:
        Canceled order.

    Raises:
        HTTPException: If the order does not exist or is no longer active.
    """

    try:
        return service.cancel_order(order_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Order not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


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
