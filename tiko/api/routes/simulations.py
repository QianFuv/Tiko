"""Simulation lifecycle routes."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.market import MarketEvent
from tiko.domain.memory import MemoryEntry, MemorySearchResult, MemoryType
from tiko.domain.observation import Observation
from tiko.domain.security import Principal
from tiko.domain.simulation import SimulationRun
from tiko.services import AuditService, SimulationService
from tiko.simulation.state import SimulationStepResult

router = APIRouter(prefix="/simulations", tags=["simulations"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageSimulationPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_simulations"))
]
ManageResearchPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_research"))
]


class SimulationCreateRequest(BaseModel):
    """Represent a request to create an in-memory simulation run."""

    name: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    start_sim_time: datetime | None = None
    mode: Literal["live_simulated_clock", "synthetic_market"] = "synthetic_market"
    end_sim_time: datetime | None = None
    speed_multiplier: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    timeframe: str = Field(default="1h", min_length=1)
    decision_interval: str = Field(default="1h", min_length=1)
    initial_equity: Decimal | None = Field(default=None, gt=Decimal("0"))


class SimulationStepRequest(BaseModel):
    """Represent a request to advance one simulation step."""

    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class SimulationSpeedRequest(BaseModel):
    """Represent a request to update simulation speed."""

    speed_multiplier: Decimal = Field(gt=Decimal("0"))


class MemoryEntryCreateRequest(BaseModel):
    """Represent a request to create auxiliary simulation memory."""

    memory_type: MemoryType
    summary: str = Field(min_length=1)
    content: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    available_at_sim_time: datetime | None = None
    decision_id: UUID | None = None


@router.get("", response_model=list[SimulationRun])
def list_simulations(service: SimulationServiceDep) -> list[SimulationRun]:
    """List process-local simulation runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Simulation runs.
    """

    return service.list_runs()


@router.post("", response_model=SimulationRun)
def create_simulation(
    request: SimulationCreateRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimulationRun:
    """Create an in-memory simulation run.

    Args:
        request: Simulation creation request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created simulation run.
    """

    try:
        run = service.create_run(
            name=request.name,
            symbols=request.symbols,
            start_sim_time=request.start_sim_time,
            mode=request.mode,
            end_sim_time=request.end_sim_time,
            speed_multiplier=request.speed_multiplier,
            timeframe=request.timeframe,
            decision_interval=request.decision_interval,
            initial_equity=request.initial_equity,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit_service.record(
        principal=principal,
        action="simulation.create",
        resource_type="simulation_run",
        resource_id=str(run.run_id),
        metadata={"name": run.name, "symbols": run.symbols},
    )
    return run


@router.get("/{run_id}", response_model=SimulationRun)
def get_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
) -> SimulationRun:
    """Get one simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Simulation run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/{run_id}/status", response_model=SimulationRun)
def get_simulation_status(
    run_id: UUID,
    service: SimulationServiceDep,
) -> SimulationRun:
    """Get current simulation status.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Simulation run status.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.get_run(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.post("/{run_id}/start", response_model=SimulationRun)
def start_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimulationRun:
    """Start a simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated simulation run.
    """

    return update_simulation_lifecycle(
        run_id=run_id,
        status="running",
        action="simulation.start",
        service=service,
        audit_service=audit_service,
        principal=principal,
    )


@router.post("/{run_id}/pause", response_model=SimulationRun)
def pause_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimulationRun:
    """Pause a simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated simulation run.
    """

    return update_simulation_lifecycle(
        run_id=run_id,
        status="paused",
        action="simulation.pause",
        service=service,
        audit_service=audit_service,
        principal=principal,
    )


@router.post("/{run_id}/resume", response_model=SimulationRun)
def resume_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimulationRun:
    """Resume a simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated simulation run.
    """

    return update_simulation_lifecycle(
        run_id=run_id,
        status="running",
        action="simulation.resume",
        service=service,
        audit_service=audit_service,
        principal=principal,
    )


@router.post("/{run_id}/stop", response_model=SimulationRun)
def stop_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimulationRun:
    """Stop a simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated simulation run.
    """

    return update_simulation_lifecycle(
        run_id=run_id,
        status="stopped",
        action="simulation.stop",
        service=service,
        audit_service=audit_service,
        principal=principal,
    )


@router.post("/{run_id}/speed", response_model=SimulationRun)
def update_simulation_speed(
    run_id: UUID,
    request: SimulationSpeedRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> SimulationRun:
    """Update a simulation run speed multiplier.

    Args:
        run_id: Simulation run identifier.
        request: Speed update request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated simulation run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        run = service.update_run_speed(run_id, request.speed_multiplier)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    audit_service.record(
        principal=principal,
        action="simulation.speed.update",
        resource_type="simulation_run",
        resource_id=str(run_id),
        metadata={"speed_multiplier": str(run.speed_multiplier)},
    )
    return run


def update_simulation_lifecycle(
    run_id: UUID,
    status: Literal["created", "running", "paused", "stopped", "completed"],
    action: str,
    service: SimulationService,
    audit_service: AuditService,
    principal: Principal,
) -> SimulationRun:
    """Update simulation lifecycle and audit the command.

    Args:
        run_id: Simulation run identifier.
        status: New simulation status.
        action: Audit action.
        service: Simulation service.
        audit_service: Audit service.
        principal: Authorized caller principal.

    Returns:
        Updated simulation run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        run = service.update_run_status(run_id, status)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    audit_service.record(
        principal=principal,
        action=action,
        resource_type="simulation_run",
        resource_id=str(run_id),
        metadata={"status": run.status},
    )
    return run


@router.get("/{run_id}/events", response_model=list[MarketEvent])
def list_simulation_events(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[MarketEvent]:
    """List market events emitted by a simulation run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Market events for the run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_events(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/{run_id}/observations/{symbol}", response_model=Observation)
def get_simulation_observation(
    run_id: UUID,
    symbol: str,
    service: SimulationServiceDep,
) -> Observation:
    """Build a point-in-time observation for a run and symbol.

    Args:
        run_id: Simulation run identifier.
        symbol: Symbol to observe.
        service: Simulation service dependency.

    Returns:
        Point-in-time observation.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.build_observation(run_id, symbol)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/{run_id}/memory", response_model=list[MemoryEntry])
def list_simulation_memory(
    run_id: UUID,
    service: SimulationServiceDep,
) -> list[MemoryEntry]:
    """List auxiliary memory entries for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.

    Returns:
        Memory entries for the run.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_memory_entries(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/{run_id}/memory/search", response_model=list[MemorySearchResult])
def search_simulation_memory(
    run_id: UUID,
    service: SimulationServiceDep,
    query: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    as_of: datetime | None = None,
) -> list[MemorySearchResult]:
    """Search auxiliary memory entries for a run.

    Args:
        run_id: Simulation run identifier.
        service: Simulation service dependency.
        query: Memory retrieval query.
        limit: Maximum result count.
        as_of: Optional simulated-time cutoff.

    Returns:
        Ranked memory search results.

    Raises:
        HTTPException: If the run does not exist or query parameters are invalid.
    """

    try:
        return service.search_memory_entries(
            run_id=run_id,
            query=query,
            as_of=as_of,
            limit=limit,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{run_id}/memory", response_model=MemoryEntry)
def create_simulation_memory(
    run_id: UUID,
    request: MemoryEntryCreateRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> MemoryEntry:
    """Create an auxiliary memory entry for a run.

    Args:
        run_id: Simulation run identifier.
        request: Memory creation request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created memory entry.

    Raises:
        HTTPException: If the run does not exist or the decision reference is invalid.
    """

    try:
        entry = service.create_memory_entry(
            run_id=run_id,
            memory_type=request.memory_type,
            summary=request.summary,
            content=request.content,
            tags=request.tags,
            available_at_sim_time=request.available_at_sim_time,
            decision_id=request.decision_id,
        )
        audit_service.record(
            principal=principal,
            action="simulation.memory.create",
            resource_type="memory_entry",
            resource_id=str(entry.memory_id),
            metadata={"run_id": str(run_id), "memory_type": entry.memory_type},
        )
        return entry
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{run_id}/step", response_model=SimulationStepResult)
def step_simulation(
    run_id: UUID,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
    request: SimulationStepRequest | None = None,
) -> SimulationStepResult:
    """Advance one simulation run by one step.

    Args:
        run_id: Simulation run identifier.
        request: Optional simulation step request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Simulation step result.

    Raises:
        HTTPException: If the run does not exist.
    """

    confidence = request.confidence if request is not None else 0.7
    try:
        result = service.step_run(run_id, confidence=confidence)
        audit_service.record(
            principal=principal,
            action="simulation.step",
            resource_type="simulation_run",
            resource_id=str(run_id),
            metadata={
                "confidence": confidence,
                "decision_id": str(result.decision.decision_id),
            },
        )
        return result
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
