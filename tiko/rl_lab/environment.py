"""Deterministic advisory RL environment for research workflows."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import uuid4

from tiko.domain.market import Candle, MarketEvent
from tiko.domain.observation import Observation
from tiko.domain.rl import EnvironmentStep, RewardBreakdown, RewardComponents, RlAction
from tiko.domain.simulation import SimulationRun
from tiko.observation import ObservationBuilder

ACTION_TARGET_WEIGHTS: dict[int, Decimal] = {
    0: Decimal("0"),
    1: Decimal("0.10"),
    2: Decimal("0.25"),
    3: Decimal("0.50"),
    4: Decimal("-0.10"),
    5: Decimal("-0.25"),
    6: Decimal("-0.50"),
}


class TradingEnvironment:
    """Provide an advisory RL environment over point-in-time candles."""

    def __init__(
        self,
        run: SimulationRun,
        candles: Sequence[Candle],
        events: Sequence[MarketEvent] | None = None,
    ) -> None:
        """Initialize the environment.

        Args:
            run: Simulation run used as immutable account context.
            candles: Ordered point-in-time candles.
            events: Optional market events available to observations.

        Raises:
            ValueError: If no candles are provided.
        """

        if len(candles) == 0:
            raise ValueError("TradingEnvironment requires at least one candle.")
        self._run = run
        self._candles = list(candles)
        self._events = list(events or [])
        self._builder = ObservationBuilder()
        self._index = 0
        self._previous_target_weight = Decimal("0")

    def reset(self, seed: int | None = None) -> Observation:
        """Reset the environment to the first point-in-time observation.

        Args:
            seed: Optional deterministic seed reserved for future scenarios.

        Returns:
            Initial observation.
        """

        _seed = seed
        self._index = 0
        self._previous_target_weight = Decimal("0")
        return self._build_observation()

    def step(self, action: RlAction) -> EnvironmentStep:
        """Advance the environment by one candle using an advisory action.

        Args:
            action: Advisory RL action.

        Returns:
            Environment transition result.
        """

        target_weight, is_invalid_action = map_discrete_action(action)
        previous_candle = self._candles[self._index]
        if self._index < len(self._candles) - 1:
            self._index += 1
        current_candle = self._candles[self._index]
        components = build_reward_components(
            previous_close=previous_candle.close,
            current_close=current_candle.close,
            target_weight=target_weight,
            previous_target_weight=self._previous_target_weight,
            is_invalid_action=is_invalid_action,
        )
        self._previous_target_weight = target_weight
        reward = calculate_reward(components)
        return EnvironmentStep(
            observation=self._build_observation(),
            action=action,
            target_weight=target_weight,
            reward=reward.reward,
            done=self._index == len(self._candles) - 1,
            info={
                "reward": str(reward.reward),
                "target_weight": str(target_weight),
                "invalid_action": is_invalid_action,
            },
        )

    def _build_observation(self) -> Observation:
        """Build the current point-in-time observation.

        Returns:
            Current observation.
        """

        current_candle = self._candles[self._index]
        available_candles = self._candles[: self._index + 1]
        available_events = [
            event
            for event in self._events
            if event.simulated_time <= current_candle.as_of
        ]
        return self._builder.build(
            run=self._run.model_copy(update={"current_sim_time": current_candle.as_of}),
            symbol=current_candle.symbol,
            as_of=current_candle.as_of,
            candles=available_candles,
            events=available_events,
            observation_id=uuid4(),
        )


def map_discrete_action(action: RlAction) -> tuple[Decimal, bool]:
    """Map a documented discrete action to a target weight.

    Args:
        action: Advisory RL action.

    Returns:
        Target weight and invalid-action flag.
    """

    target_weight = ACTION_TARGET_WEIGHTS.get(action.action_id)
    if target_weight is None:
        return Decimal("0"), True
    return target_weight, False


def build_reward_components(
    previous_close: Decimal,
    current_close: Decimal,
    target_weight: Decimal,
    previous_target_weight: Decimal,
    is_invalid_action: bool,
) -> RewardComponents:
    """Build deterministic reward components from price movement and action.

    Args:
        previous_close: Previous close price.
        current_close: Current close price.
        target_weight: Current target weight.
        previous_target_weight: Previous target weight.
        is_invalid_action: Whether the action was outside the documented set.

    Returns:
        Reward components.
    """

    price_return = (current_close - previous_close) / previous_close
    turnover = abs(target_weight - previous_target_weight)
    return RewardComponents(
        portfolio_return=target_weight * price_return,
        fee_cost=turnover * Decimal("0.0005"),
        slippage_cost=turnover * Decimal("0.0003"),
        funding_cost=Decimal("0"),
        drawdown_penalty=max(Decimal("0"), -target_weight * price_return),
        leverage_penalty=max(Decimal("0"), abs(target_weight) - Decimal("1")),
        turnover_penalty=turnover * Decimal("0.0002"),
        invalid_action_penalty=Decimal("1") if is_invalid_action else Decimal("0"),
    )


def calculate_reward(components: RewardComponents) -> RewardBreakdown:
    """Calculate reward from explicit architecture components.

    Args:
        components: Reward component values.

    Returns:
        Reward breakdown.
    """

    reward = (
        components.portfolio_return
        - components.fee_cost
        - components.slippage_cost
        - components.funding_cost
        - components.drawdown_penalty
        - components.leverage_penalty
        - components.turnover_penalty
        - components.invalid_action_penalty
    )
    return RewardBreakdown(components=components, reward=reward)
