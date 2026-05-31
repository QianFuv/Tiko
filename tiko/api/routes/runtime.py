"""Runtime job, heartbeat, and watchdog routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_runtime_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.reporting import Alert
from tiko.domain.runtime import (
    BackgroundJob,
    WatchdogReport,
    WorkerHeartbeat,
    WorkerStatus,
)
from tiko.domain.security import Principal
from tiko.services import AuditService, RuntimeService, SimulationService

router = APIRouter(prefix="/runtime", tags=["runtime"])
RuntimeServiceDep = Annotated[RuntimeService, Depends(get_runtime_service)]
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageRuntimePrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_runtime"))
]


class WorkerHeartbeatRequest(BaseModel):
    """Represent a worker heartbeat update request."""

    worker_name: str = Field(min_length=1)
    worker_status: WorkerStatus = "healthy"
    event_queue_depth: int = Field(default=0, ge=0)
    clock_lag_ms: int = Field(default=0, ge=0)


@router.get("/jobs", response_model=list[BackgroundJob])
def list_runtime_jobs(service: RuntimeServiceDep) -> list[BackgroundJob]:
    """List runtime jobs.

    Args:
        service: Runtime service dependency.

    Returns:
        Runtime job records.
    """

    return service.list_jobs()


@router.get("/jobs/{job_id}", response_model=BackgroundJob)
def get_runtime_job(
    job_id: UUID,
    service: RuntimeServiceDep,
) -> BackgroundJob:
    """Get one runtime job.

    Args:
        job_id: Runtime job identifier.
        service: Runtime service dependency.

    Returns:
        Runtime job.

    Raises:
        HTTPException: If the job does not exist.
    """

    try:
        return service.get_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Runtime job not found.") from error


@router.get("/heartbeats", response_model=list[WorkerHeartbeat])
def list_worker_heartbeats(service: RuntimeServiceDep) -> list[WorkerHeartbeat]:
    """List latest worker heartbeats.

    Args:
        service: Runtime service dependency.

    Returns:
        Worker heartbeat records.
    """

    return service.list_heartbeats()


@router.post("/heartbeats", response_model=WorkerHeartbeat)
def record_worker_heartbeat(
    request: WorkerHeartbeatRequest,
    service: RuntimeServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageRuntimePrincipalDep,
) -> WorkerHeartbeat:
    """Record one worker heartbeat.

    Args:
        request: Worker heartbeat payload.
        service: Runtime service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Recorded worker heartbeat.
    """

    heartbeat = service.record_heartbeat(
        worker_name=request.worker_name,
        worker_status=request.worker_status,
        event_queue_depth=request.event_queue_depth,
        clock_lag_ms=request.clock_lag_ms,
    )
    audit_service.record(
        principal=principal,
        action="runtime.heartbeat.record",
        resource_type="worker",
        resource_id=heartbeat.worker_name,
        metadata={
            "worker_status": heartbeat.worker_status,
            "event_queue_depth": heartbeat.event_queue_depth,
            "clock_lag_ms": heartbeat.clock_lag_ms,
        },
    )
    return heartbeat


@router.post("/watchdog", response_model=WatchdogReport)
def run_runtime_watchdog(
    service: RuntimeServiceDep,
    simulation_service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageRuntimePrincipalDep,
) -> WatchdogReport:
    """Run runtime watchdog checks.

    Args:
        service: Runtime service dependency.
        simulation_service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Watchdog report.
    """

    runs = simulation_service.list_runs()
    report = service.run_watchdog(
        simulation_runs=runs,
        alerts=list_watchdog_alerts(simulation_service),
        orders=simulation_service.list_orders(),
    )
    audit_service.record(
        principal=principal,
        action="runtime.watchdog.run",
        resource_type="watchdog_report",
        resource_id=str(report.report_id),
        metadata={
            "worker_status": report.worker_status,
            "queued_job_count": report.queued_job_count,
            "check_count": len(report.checks),
        },
    )
    return report


def list_watchdog_alerts(simulation_service: SimulationService) -> list[Alert]:
    """List alerts available to the runtime watchdog.

    Args:
        simulation_service: Simulation service dependency.

    Returns:
        Alerts from all known simulation runs.
    """

    alerts: list[Alert] = []
    for run in simulation_service.list_runs():
        try:
            alerts.extend(simulation_service.list_alerts(run.run_id))
        except KeyError:
            continue
    return alerts
