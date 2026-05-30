"""Market data policy and symbol routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tiko.api.dependencies import get_simulation_service
from tiko.services import SimulationService

router = APIRouter(prefix="/market", tags=["market"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


class MarketSymbolsResponse(BaseModel):
    """Represent symbols available to the simulated environment."""

    symbols: list[str]
    data_policy: str
    private_methods_allowed: bool


@router.get("/symbols", response_model=MarketSymbolsResponse)
def list_market_symbols(service: SimulationServiceDep) -> MarketSymbolsResponse:
    """Return symbols known from runs or default demo symbols.

    Args:
        service: Simulation service dependency.

    Returns:
        Market symbols and read-only policy.
    """

    symbols = sorted({symbol for run in service.list_runs() for symbol in run.symbols})
    return MarketSymbolsResponse(
        symbols=symbols or ["BTCUSDT", "ETHUSDT"],
        data_policy="read_only_public_market_data",
        private_methods_allowed=False,
    )
