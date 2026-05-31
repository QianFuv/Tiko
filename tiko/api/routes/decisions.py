"""Decision query and posterior review routes."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import get_simulation_service
from tiko.domain.decision import DecisionReview, TradeIntent
from tiko.services import SimulationService

router = APIRouter(prefix="/decisions", tags=["decisions"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


class DecisionReviewCreateRequest(BaseModel):
    """Represent a request to create posterior decision review metrics."""

    horizon: str = Field(min_length=1)
    realized_return: Decimal
    max_adverse_excursion: Decimal
    max_favorable_excursion: Decimal
    was_correct_directionally: bool
    error_tags: list[str] = Field(default_factory=list)
    reviewer_summary: str = Field(min_length=1)


@router.get("", response_model=list[TradeIntent])
def list_decisions(service: SimulationServiceDep) -> list[TradeIntent]:
    """List generated structured trade intents.

    Args:
        service: Simulation service dependency.

    Returns:
        Structured trade intents.
    """

    return service.list_decisions()


@router.post("/{decision_id}/review", response_model=DecisionReview)
def create_decision_review(
    decision_id: UUID,
    request: DecisionReviewCreateRequest,
    service: SimulationServiceDep,
) -> DecisionReview:
    """Create posterior review metrics for a decision.

    Args:
        decision_id: Trade intent identifier.
        request: Review creation payload.
        service: Simulation service dependency.

    Returns:
        Created decision review.

    Raises:
        HTTPException: If the decision does not exist.
    """

    try:
        return service.create_decision_review(
            decision_id=decision_id,
            horizon=request.horizon,
            realized_return=request.realized_return,
            max_adverse_excursion=request.max_adverse_excursion,
            max_favorable_excursion=request.max_favorable_excursion,
            was_correct_directionally=request.was_correct_directionally,
            error_tags=request.error_tags,
            reviewer_summary=request.reviewer_summary,
        )
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
