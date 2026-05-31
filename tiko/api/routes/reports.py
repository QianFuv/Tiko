"""Report routes for simulation review artifacts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from tiko.api.dependencies import (
    get_audit_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.reporting import ReportArtifact
from tiko.domain.security import Principal
from tiko.services import AuditService, SimulationService

router = APIRouter(prefix="/reports", tags=["reports"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageReportsPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_reports"))
]


@router.post("/simulations/{run_id}", response_model=ReportArtifact)
def create_simulation_report(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageReportsPrincipalDep,
) -> ReportArtifact:
    """Create a structured simulation report.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created report artifact.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        report = service.create_simulation_report(run_id)
        audit_service.record(
            principal=principal,
            action="report.simulation.create",
            resource_type="report",
            resource_id=str(report.report_id),
            metadata={"run_id": str(run_id), "report_type": report.report_type},
        )
        return report
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/simulations/{run_id}", response_model=list[ReportArtifact])
def list_simulation_reports(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[ReportArtifact]:
    """List structured simulation reports.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Report artifacts.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_reports(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
