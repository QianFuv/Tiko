"""Agent runtime routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tiko.agents import AgentRuntime, AgentRuntimeError, RuleBasedTraderAgent
from tiko.domain.decision import TradeIntent
from tiko.domain.observation import Observation

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentInfoResponse(BaseModel):
    """Represent an available deterministic agent."""

    agent_id: str
    agent_type: str
    live_trading_allowed: bool


@router.get("", response_model=list[AgentInfoResponse])
def list_agents() -> list[AgentInfoResponse]:
    """List available agent runtimes.

    Returns:
        Available agent metadata.
    """

    return [
        AgentInfoResponse(
            agent_id="rule_based_trader",
            agent_type="rule_based",
            live_trading_allowed=False,
        )
    ]


@router.post("/rule-based/evaluate", response_model=TradeIntent)
def evaluate_rule_based_agent(observation: Observation) -> TradeIntent:
    """Evaluate the deterministic rule-based agent for one observation.

    Args:
        observation: Point-in-time observation.

    Returns:
        Structured trade intent.

    Raises:
        HTTPException: If agent output violates runtime scope.
    """

    try:
        return AgentRuntime(RuleBasedTraderAgent()).evaluate(observation)
    except AgentRuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
