"""Report routes for simulation review artifacts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from tiko.api.dependencies import (
    get_audit_service,
    get_experiment_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.reporting import RenderedReport, ReportArtifact, ReportFormat
from tiko.domain.security import Principal
from tiko.services import (
    AuditService,
    ExperimentService,
    ReportRenderService,
    SimulationService,
)

router = APIRouter(prefix="/reports", tags=["reports"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
ExperimentServiceDep = Annotated[ExperimentService, Depends(get_experiment_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageReportsPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_reports"))
]
ReportFormatQuery = Annotated[ReportFormat, Query(alias="format")]


def find_report_artifact(
    report_id: UUID,
    simulation_service: SimulationService,
    experiment_service: ExperimentService,
) -> ReportArtifact:
    """Find a report artifact across simulation and experiment services.

    Args:
        report_id: Report identifier.
        simulation_service: Simulation service dependency.
        experiment_service: Experiment service dependency.

    Returns:
        Report artifact.

    Raises:
        HTTPException: If the report does not exist.
    """

    try:
        return simulation_service.get_report(report_id)
    except KeyError:
        try:
            return experiment_service.get_report(report_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Report not found.") from error


@router.get("/{report_id}", response_model=ReportArtifact)
def get_report(
    report_id: UUID,
    simulation_service: SimulationServiceDep,
    experiment_service: ExperimentServiceDep,
) -> ReportArtifact:
    """Get one process-local report by ID.

    Args:
        report_id: Report identifier.
        simulation_service: Simulation service dependency.
        experiment_service: Experiment service dependency.

    Returns:
        Report artifact.

    Raises:
        HTTPException: If the report does not exist.
    """

    return find_report_artifact(report_id, simulation_service, experiment_service)


@router.get("/{report_id}/render", response_model=RenderedReport)
def render_report(
    report_id: UUID,
    simulation_service: SimulationServiceDep,
    experiment_service: ExperimentServiceDep,
    report_format: ReportFormatQuery = "markdown",
) -> RenderedReport:
    """Render one report by ID.

    Args:
        report_id: Report identifier.
        simulation_service: Simulation service dependency.
        experiment_service: Experiment service dependency.
        report_format: Requested report render format.

    Returns:
        Rendered report document.

    Raises:
        HTTPException: If the report does not exist.
    """

    report = find_report_artifact(report_id, simulation_service, experiment_service)
    return ReportRenderService().render(report, report_format=report_format)


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


@router.post("/decisions/{decision_id}", response_model=ReportArtifact)
def create_decision_report(
    decision_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageReportsPrincipalDep,
) -> ReportArtifact:
    """Create a structured decision report.

    Args:
        decision_id: Trade intent identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created decision report.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        report = service.create_decision_report(decision_id)
        audit_service.record(
            principal=principal,
            action="report.decision.create",
            resource_type="report",
            resource_id=str(report.report_id),
            metadata={
                "decision_id": str(decision_id),
                "report_type": report.report_type,
            },
        )
        return report
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error


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


@router.get("/decisions/{decision_id}", response_model=list[ReportArtifact])
def list_decision_reports(
    decision_id: UUID,
    service: SimulationServiceDep,
) -> list[ReportArtifact]:
    """List structured decision reports.

    Args:
        decision_id: Trade intent identifier.
        service: Simulation service dependency.

    Returns:
        Decision report artifacts.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        return service.list_decision_reports(decision_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error


@router.post("/experiments/{experiment_id}", response_model=ReportArtifact)
def create_experiment_report(
    experiment_id: UUID,
    service: ExperimentServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageReportsPrincipalDep,
) -> ReportArtifact:
    """Create a structured experiment report.

    Args:
        experiment_id: Experiment identifier.
        service: Experiment service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created experiment report.

    Raises:
        HTTPException: If the experiment does not exist.
    """

    try:
        report = service.create_experiment_report(experiment_id)
        audit_service.record(
            principal=principal,
            action="report.experiment.create",
            resource_type="report",
            resource_id=str(report.report_id),
            metadata={
                "experiment_id": str(experiment_id),
                "report_type": report.report_type,
            },
        )
        return report
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Experiment not found.") from error


@router.get("/experiments/{experiment_id}", response_model=list[ReportArtifact])
def list_experiment_reports(
    experiment_id: UUID,
    service: ExperimentServiceDep,
) -> list[ReportArtifact]:
    """List structured experiment reports.

    Args:
        experiment_id: Experiment identifier.
        service: Experiment service dependency.

    Returns:
        Experiment report artifacts.

    Raises:
        HTTPException: If the experiment does not exist.
    """

    try:
        return service.list_experiment_reports(experiment_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Experiment not found.") from error
