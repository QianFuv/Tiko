"""Portfolio summary routes for simulated account state."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tiko.api.dependencies import get_simulation_service
from tiko.services import SimulationService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


class PortfolioSummaryResponse(BaseModel):
    """Represent simulated portfolio summary values."""

    run_id: UUID
    base_currency: str
    cash_balance: Decimal
    total_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_drawdown: Decimal
    gross_exposure: Decimal


@router.get("/{run_id}/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    run_id: UUID,
    service: SimulationServiceDep,
) -> PortfolioSummaryResponse:
    """Return simulated portfolio summary for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Simulated portfolio summary.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        run = service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    return PortfolioSummaryResponse(
        run_id=run_id,
        base_currency=run.account.base_currency,
        cash_balance=run.account.cash_balance,
        total_equity=run.account.total_equity,
        realized_pnl=run.account.realized_pnl,
        unrealized_pnl=run.account.unrealized_pnl,
        max_drawdown=run.account.max_drawdown,
        gross_exposure=Decimal("0"),
    )
