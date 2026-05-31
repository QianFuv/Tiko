"""Agent traceability schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel
from tiko.domain.decision import TradeIntent
from tiko.domain.order import Fill, SimOrder
from tiko.domain.risk import RiskReview

AgentRunStatus = Literal["completed", "failed", "replayed"]
AgentMessageRole = Literal["system", "observation", "assistant", "critic", "risk"]


class AgentRun(DomainModel):
    """Represent an agent evaluation associated with a decision."""

    agent_run_id: UUID
    run_id: UUID
    decision_id: UUID
    agent_id: str = Field(min_length=1)
    status: AgentRunStatus
    started_at_sim_time: datetime
    completed_at_sim_time: datetime


class AgentMessage(DomainModel):
    """Represent a structured trace message for an agent run."""

    message_id: UUID
    agent_run_id: UUID
    role: AgentMessageRole
    content: dict[str, object]
    created_at_sim_time: datetime


class DecisionTrace(DomainModel):
    """Represent joined traceability artifacts for one decision."""

    decision: TradeIntent
    agent_run: AgentRun
    messages: list[AgentMessage]
    risk_review: RiskReview | None = None
    order: SimOrder | None = None
    fill: Fill | None = None
