"""Decision query and posterior review routes."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.agent import DecisionTrace
from tiko.domain.decision import DecisionReview, TradeIntent
from tiko.domain.memory import MemoryEntry
from tiko.domain.security import Principal
from tiko.services import AuditService, SimulationService

router = APIRouter(prefix="/decisions", tags=["decisions"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageResearchPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_research"))
]


class DecisionReviewCreateRequest(BaseModel):
    """Represent a request to create posterior decision review metrics."""

    horizon: str = Field(min_length=1)
    realized_return: Decimal
    max_adverse_excursion: Decimal
    max_favorable_excursion: Decimal
    was_correct_directionally: bool
    error_tags: list[str] = Field(default_factory=list)
    reviewer_summary: str = Field(min_length=1)


class DecisionAnnotationRequest(BaseModel):
    """Represent a request to annotate a decision trace."""

    summary: str = Field(min_length=1)
    content: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


@router.get("", response_model=list[TradeIntent])
def list_decisions(service: SimulationServiceDep) -> list[TradeIntent]:
    """List generated structured trade intents.

    Args:
        service: Simulation service dependency.

    Returns:
        Structured trade intents.
    """

    return service.list_decisions()


@router.get("/{decision_id}", response_model=TradeIntent)
def get_decision(
    decision_id: UUID,
    service: SimulationServiceDep,
) -> TradeIntent:
    """Get one structured trade intent.

    Args:
        decision_id: Trade intent identifier.
        service: Simulation service dependency.

    Returns:
        Trade intent.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        return service.get_decision(decision_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error


@router.get("/{decision_id}/trace", response_model=DecisionTrace)
def get_decision_trace(
    decision_id: UUID,
    service: SimulationServiceDep,
) -> DecisionTrace:
    """Get joined trace artifacts for one decision.

    Args:
        decision_id: Trade intent identifier.
        service: Simulation service dependency.

    Returns:
        Decision trace.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        return service.build_decision_trace(decision_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error


@router.post("/{decision_id}/annotate", response_model=MemoryEntry)
def annotate_decision(
    decision_id: UUID,
    request: DecisionAnnotationRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> MemoryEntry:
    """Annotate one decision trace.

    Args:
        decision_id: Trade intent identifier.
        request: Annotation request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created decision memory entry.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        memory = service.annotate_decision(
            decision_id=decision_id,
            summary=request.summary,
            content=request.content,
            tags=request.tags,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error
    audit_service.record(
        principal=principal,
        action="decision.annotate",
        resource_type="decision",
        resource_id=str(decision_id),
        metadata={"memory_id": str(memory.memory_id)},
    )
    return memory


@router.post("/{decision_id}/review", response_model=DecisionReview)
def create_decision_review(
    decision_id: UUID,
    request: DecisionReviewCreateRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageResearchPrincipalDep,
) -> DecisionReview:
    """Create posterior review metrics for a decision.

    Args:
        decision_id: Trade intent identifier.
        request: Review creation payload.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Created decision review.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        review = service.create_decision_review(
            decision_id=decision_id,
            horizon=request.horizon,
            realized_return=request.realized_return,
            max_adverse_excursion=request.max_adverse_excursion,
            max_favorable_excursion=request.max_favorable_excursion,
            was_correct_directionally=request.was_correct_directionally,
            error_tags=request.error_tags,
            reviewer_summary=request.reviewer_summary,
        )
        audit_service.record(
            principal=principal,
            action="decision.review.create",
            resource_type="decision_review",
            resource_id=str(review.review_id),
            metadata={"decision_id": str(decision_id), "horizon": review.horizon},
        )
        return review
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error


@router.get("/{decision_id}/review", response_model=list[DecisionReview])
def list_decision_reviews(
    decision_id: UUID,
    service: SimulationServiceDep,
) -> list[DecisionReview]:
    """List posterior review metrics for a decision.

    Args:
        decision_id: Trade intent identifier.
        service: Simulation service dependency.

    Returns:
        Decision reviews.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        return service.list_decision_reviews(decision_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision not found.") from error
