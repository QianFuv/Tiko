"""Risk policy and review routes."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.reporting import Alert, AlertCategory, AlertSeverity, AlertStatus
from tiko.domain.risk import RiskLimits, RiskReview
from tiko.domain.security import Principal
from tiko.services import AuditService, SimulationService

router = APIRouter(prefix="/risk", tags=["risk"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageAlertsPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_alerts"))
]


class RiskLimitsUpdateRequest(BaseModel):
    """Represent a request to update run-level risk limits."""

    minimum_confidence: float = Field(ge=0.0, le=1.0)
    minimum_data_quality_score: float = Field(ge=0.0, le=1.0)
    max_target_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    max_order_notional: Decimal = Field(ge=Decimal("0"))
    max_drawdown: Decimal = Field(default=Decimal("0.20"), ge=Decimal("0"))
    max_daily_loss: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))


class AlertCreateRequest(BaseModel):
    """Represent a request to create a run alert."""

    category: AlertCategory
    severity: AlertSeverity
    message: str


class AlertStatusUpdateRequest(BaseModel):
    """Represent a request to update a run alert status."""

    status: AlertStatus


@router.get("/{run_id}/limits", response_model=RiskLimits)
def get_risk_limits(
    run_id: UUID,
    service: SimulationServiceDep,
) -> RiskLimits:
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
        return service.get_risk_limits(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.put("/{run_id}/limits", response_model=RiskLimits)
def update_risk_limits(
    run_id: UUID,
    request: RiskLimitsUpdateRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageAlertsPrincipalDep,
) -> RiskLimits:
    """Update configured risk limits for a run.

    Args:
        run_id: Simulation run identifier.
        request: Risk limit update request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated risk limits.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        limits = service.update_risk_limits(
            run_id=run_id,
            minimum_confidence=request.minimum_confidence,
            minimum_data_quality_score=request.minimum_data_quality_score,
            max_target_weight=request.max_target_weight,
            max_order_notional=request.max_order_notional,
            max_drawdown=request.max_drawdown,
            max_daily_loss=request.max_daily_loss,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    audit_service.record(
        principal=principal,
        action="risk.limits.update",
        resource_type="simulation_run",
        resource_id=str(run_id),
        metadata={
            "minimum_confidence": limits.minimum_confidence,
            "minimum_data_quality_score": limits.minimum_data_quality_score,
            "max_target_weight": str(limits.max_target_weight),
            "max_order_notional": str(limits.max_order_notional),
            "max_drawdown": str(limits.max_drawdown),
            "max_daily_loss": str(limits.max_daily_loss),
        },
    )
    return limits


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
    audit_service: AuditServiceDep,
    principal: ManageAlertsPrincipalDep,
) -> Alert:
    """Create an alert for a simulation run.

    Args:
        run_id: Simulation run identifier.
        request: Alert creation request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created alert.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        alert = service.create_alert(
            run_id=run_id,
            category=request.category,
            severity=request.severity,
            message=request.message,
        )
        audit_service.record(
            principal=principal,
            action="alert.create",
            resource_type="alert",
            resource_id=str(alert.alert_id),
            metadata={"run_id": str(run_id), "category": alert.category},
        )
        return alert
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
    audit_service: AuditServiceDep,
    principal: ManageAlertsPrincipalDep,
) -> Alert:
    """Update a run alert status.

    Args:
        run_id: Simulation run identifier.
        alert_id: Alert identifier.
        request: Alert status update request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated alert.

    Raises:
        HTTPException: If the run or alert does not exist.
    """

    try:
        alert = service.update_alert_status(run_id, alert_id, request.status)
        audit_service.record(
            principal=principal,
            action="alert.status.update",
            resource_type="alert",
            resource_id=str(alert_id),
            metadata={"run_id": str(run_id), "status": alert.status},
        )
        return alert
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Alert not found.") from error


@router.get("/{run_id}/reviews", response_model=list[RiskReview])
def list_risk_reviews(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[RiskReview]:
    """List risk reviews for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Risk reviews for the run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_risk_reviews(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


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


@router.post("/{run_id}/pause", response_model=RiskLimits)
def pause_run_from_risk(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageAlertsPrincipalDep,
) -> RiskLimits:
    """Pause a run from risk controls.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Current risk limits after pause.

    Raises:
        HTTPException: If the run does not exist.
    """

    return update_risk_controlled_run_status(
        run_id=run_id,
        status="paused",
        action="risk.pause",
        service=service,
        audit_service=audit_service,
        principal=principal,
    )


@router.post("/{run_id}/resume", response_model=RiskLimits)
def resume_run_from_risk(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageAlertsPrincipalDep,
) -> RiskLimits:
    """Resume a run from risk controls.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Current risk limits after resume.

    Raises:
        HTTPException: If the run does not exist.
    """

    return update_risk_controlled_run_status(
        run_id=run_id,
        status="running",
        action="risk.resume",
        service=service,
        audit_service=audit_service,
        principal=principal,
    )


def update_risk_controlled_run_status(
    run_id: UUID,
    status: Literal["paused", "running"],
    action: str,
    service: SimulationService,
    audit_service: AuditService,
    principal: Principal,
) -> RiskLimits:
    """Update run status through risk controls and audit the command.

    Args:
        run_id: Simulation run identifier.
        status: New simulation status.
        action: Audit action.
        service: Simulation service.
        audit_service: Audit service.
        principal: Authorized caller principal.

    Returns:
        Current risk limits response.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        service.update_run_status(run_id, status)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    audit_service.record(
        principal=principal,
        action=action,
        resource_type="simulation_run",
        resource_id=str(run_id),
        metadata={"status": status},
    )
    return get_risk_limits(run_id, service)
