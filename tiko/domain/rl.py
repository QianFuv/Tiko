"""Reinforcement learning research schemas."""

from decimal import Decimal

from pydantic import Field

from tiko.domain.base import DomainModel
from tiko.domain.observation import Observation


class RlAction(DomainModel):
    """Represent an advisory RL action that cannot execute orders directly."""

    action_id: int


class RewardComponents(DomainModel):
    """Represent explicit reward inputs for deterministic evaluation."""

    portfolio_return: Decimal
    fee_cost: Decimal = Field(ge=Decimal("0"))
    slippage_cost: Decimal = Field(ge=Decimal("0"))
    funding_cost: Decimal = Field(ge=Decimal("0"))
    drawdown_penalty: Decimal = Field(ge=Decimal("0"))
    leverage_penalty: Decimal = Field(ge=Decimal("0"))
    turnover_penalty: Decimal = Field(ge=Decimal("0"))
    invalid_action_penalty: Decimal = Field(ge=Decimal("0"))


class RewardBreakdown(DomainModel):
    """Represent reward output and its reproducible components."""

    components: RewardComponents
    reward: Decimal


class EnvironmentStep(DomainModel):
    """Represent one advisory RL environment transition."""

    observation: Observation
    action: RlAction
    target_weight: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    reward: Decimal
    done: bool
    info: dict[str, object]


class RlTrainingSummary(DomainModel):
    """Represent deterministic advisory RL training output."""

    algorithm: str = Field(min_length=1)
    episode_count: int = Field(ge=1)
    best_action_id: int
    best_total_reward: Decimal
    action_rewards: dict[int, Decimal]
    metrics: dict[str, object]
