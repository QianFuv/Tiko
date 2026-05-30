"""Decision query routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from tiko.api.dependencies import get_simulation_service
from tiko.domain.decision import TradeIntent
from tiko.services import SimulationService

router = APIRouter(prefix="/decisions", tags=["decisions"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


@router.get("", response_model=list[TradeIntent])
def list_decisions(service: SimulationServiceDep) -> list[TradeIntent]:
    """List generated structured trade intents.

    Args:
        service: Simulation service dependency.

    Returns:
        Structured trade intents.
    """

    return service.list_decisions()
