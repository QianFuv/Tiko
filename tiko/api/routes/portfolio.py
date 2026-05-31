"""Portfolio summary routes for simulated account state."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tiko.api.dependencies import get_simulation_service
from tiko.domain.account import Position
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


class PortfolioSnapshotResponse(BaseModel):
    """Represent one simulated portfolio snapshot."""

    run_id: UUID
    simulated_time: datetime
    cash_balance: Decimal
    total_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_drawdown: Decimal


class PortfolioPnlResponse(BaseModel):
    """Represent current simulated PnL values."""

    run_id: UUID
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal


class PortfolioDrawdownResponse(BaseModel):
    """Represent current simulated drawdown values."""

    run_id: UUID
    max_drawdown: Decimal


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


@router.get("/{run_id}/positions", response_model=list[Position])
def list_portfolio_positions(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[Position]:
    """Return simulated positions for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Current simulated positions.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_positions(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/{run_id}/snapshots", response_model=list[PortfolioSnapshotResponse])
def list_portfolio_snapshots(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[PortfolioSnapshotResponse]:
    """Return current simulated portfolio snapshot.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Current portfolio snapshot list.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        run = service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    return [
        PortfolioSnapshotResponse(
            run_id=run_id,
            simulated_time=run.current_sim_time,
            cash_balance=run.account.cash_balance,
            total_equity=run.account.total_equity,
            realized_pnl=run.account.realized_pnl,
            unrealized_pnl=run.account.unrealized_pnl,
            max_drawdown=run.account.max_drawdown,
        )
    ]


@router.get("/{run_id}/pnl", response_model=PortfolioPnlResponse)
def get_portfolio_pnl(
    run_id: UUID,
    service: SimulationServiceDep,
) -> PortfolioPnlResponse:
    """Return current simulated PnL for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Current PnL response.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        run = service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    return PortfolioPnlResponse(
        run_id=run_id,
        realized_pnl=run.account.realized_pnl,
        unrealized_pnl=run.account.unrealized_pnl,
        total_pnl=run.account.realized_pnl + run.account.unrealized_pnl,
    )


@router.get("/{run_id}/drawdown", response_model=PortfolioDrawdownResponse)
def get_portfolio_drawdown(
    run_id: UUID,
    service: SimulationServiceDep,
) -> PortfolioDrawdownResponse:
    """Return current simulated drawdown for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Current drawdown response.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        run = service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    return PortfolioDrawdownResponse(
        run_id=run_id, max_drawdown=run.account.max_drawdown
    )
