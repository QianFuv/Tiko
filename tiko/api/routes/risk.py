"""Risk policy and review routes."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tiko.api.dependencies import get_simulation_service
from tiko.core.config import get_settings
from tiko.domain.reporting import Alert, AlertCategory, AlertSeverity, AlertStatus
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


class AlertCreateRequest(BaseModel):
    """Represent a request to create a run alert."""

    category: AlertCategory
    severity: AlertSeverity
    message: str


class AlertStatusUpdateRequest(BaseModel):
    """Represent a request to update a run alert status."""

    status: AlertStatus


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


@router.get("/{run_id}/alerts", response_model=list[Alert])
def list_alerts(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[Alert]:
    """List alerts for a simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Run alerts.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_alerts(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.post("/{run_id}/alerts", response_model=Alert)
def create_alert(
    run_id: UUID,
    request: AlertCreateRequest,
    service: SimulationServiceDep,
) -> Alert:
    """Create an alert for a simulation run.

    Args:
        run_id: Simulation run identifier.
        request: Alert creation request.
        service: Simulation service dependency.

    Returns:
        Created alert.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.create_alert(
            run_id=run_id,
            category=request.category,
            severity=request.severity,
            message=request.message,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.post("/{run_id}/alerts/{alert_id}/status", response_model=Alert)
def update_alert_status(
    run_id: UUID,
    alert_id: UUID,
    request: AlertStatusUpdateRequest,
    service: SimulationServiceDep,
) -> Alert:
    """Update a run alert status.

    Args:
        run_id: Simulation run identifier.
        alert_id: Alert identifier.
        request: Alert status update request.
        service: Simulation service dependency.

    Returns:
        Updated alert.

    Raises:
        HTTPException: If the run or alert does not exist.
    """

    try:
        return service.update_alert_status(run_id, alert_id, request.status)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Alert not found.") from error


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
