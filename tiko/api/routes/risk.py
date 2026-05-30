"""Risk policy and review routes."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tiko.api.dependencies import get_simulation_service
from tiko.core.config import get_settings
from tiko.domain.risk import RiskReview
from tiko.services import SimulationService

router = APIRouter(prefix="/risk", tags=["risk"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


class RiskLimitsResponse(BaseModel):
    """Represent active risk limits for a simulation run."""

    run_id: UUID
    minimum_confidence: float
    minimum_data_quality_score: float
    max_target_weight: Decimal
    max_order_notional: Decimal
    live_trading_allowed: bool


@router.get("/{run_id}/limits", response_model=RiskLimitsResponse)
def get_risk_limits(
    run_id: UUID,
    service: SimulationServiceDep,
) -> RiskLimitsResponse:
    """Return configured risk limits for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Risk limits response.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    settings = get_settings()
    return RiskLimitsResponse(
        run_id=run_id,
        minimum_confidence=settings.minimum_trade_confidence,
        minimum_data_quality_score=settings.minimum_data_quality_score,
        max_target_weight=settings.max_target_weight,
        max_order_notional=settings.max_order_notional,
        live_trading_allowed=False,
    )


@router.get("/{run_id}/reviews/latest", response_model=RiskReview | None)
def get_latest_risk_review(
    run_id: UUID,
    service: SimulationServiceDep,
) -> RiskReview | None:
    """Return the latest risk review for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Latest risk review or `None`.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        service.get_run(run_id)
        return service.get_latest_risk_review(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
