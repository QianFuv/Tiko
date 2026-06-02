"""Deterministic advisory RL training helpers."""

from collections.abc import Sequence
from decimal import Decimal

from tiko.domain.market import Candle, MarketEvent
from tiko.domain.rl import (
    RlAction,
    RlModelCard,
    RlTrainingSummary,
    RlWalkForwardEvaluation,
)
from tiko.domain.simulation import SimulationRun
from tiko.rl_lab.environment import ACTION_TARGET_WEIGHTS, TradingEnvironment

STATIC_POLICY_REWARD_COMPONENTS = [
    "portfolio_return",
    "fee_cost",
    "slippage_cost",
    "funding_cost",
    "drawdown_penalty",
    "leverage_penalty",
    "turnover_penalty",
    "invalid_action_penalty",
]


def train_static_policy(
    run: SimulationRun,
    candles: Sequence[Candle],
    events: Sequence[MarketEvent] | None = None,
    candidate_action_ids: Sequence[int] | None = None,
) -> RlTrainingSummary:
    """Train a deterministic static discrete-action policy.

    Args:
        run: Simulation run used as immutable account context.
        candles: Ordered point-in-time candles.
        events: Optional market events available to observations.
        candidate_action_ids: Optional candidate discrete actions. Documented
            actions are used when omitted.

    Returns:
        Training summary for the best static action.

    Raises:
        ValueError: If no candidate actions are provided.
    """

    action_ids = tuple(
        candidate_action_ids
        if candidate_action_ids is not None
        else sorted(ACTION_TARGET_WEIGHTS)
    )
    if len(action_ids) == 0:
        raise ValueError("Static policy training requires at least one action.")

    action_rewards = {
        action_id: _evaluate_static_action(run, candles, events, action_id)
        for action_id in action_ids
    }
    best_action_id, best_total_reward = min(
        action_rewards.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return RlTrainingSummary(
        algorithm="static_discrete_policy_search",
        episode_count=len(action_ids),
        best_action_id=best_action_id,
        best_total_reward=best_total_reward,
        action_rewards=action_rewards,
        metrics={
            "candidate_action_count": len(action_ids),
            "best_target_weight": str(ACTION_TARGET_WEIGHTS.get(best_action_id, 0)),
        },
    )


def build_static_policy_model_card(summary: RlTrainingSummary) -> RlModelCard:
    """Build review metadata for a static policy training summary.

    Args:
        summary: Static policy training summary.

    Returns:
        Structured RL model card.
    """

    best_target_weight = ACTION_TARGET_WEIGHTS.get(summary.best_action_id, Decimal("0"))
    return RlModelCard(
        algorithm=summary.algorithm,
        policy_type="static_discrete_action_policy",
        action_space={
            action_id: str(target_weight)
            for action_id, target_weight in sorted(ACTION_TARGET_WEIGHTS.items())
        },
        best_action_id=summary.best_action_id,
        best_target_weight=best_target_weight,
        episode_count=summary.episode_count,
        reward_components=list(STATIC_POLICY_REWARD_COMPONENTS),
        intended_use="Advisory simulation research signal only; not live execution.",
        limitations=[
            "Static action search does not learn a state-dependent policy.",
            "Rewards are evaluated on the supplied candle window only.",
            (
                "Policy output must pass agent, risk, portfolio, "
                "and simulated broker gates."
            ),
        ],
        metrics={
            **summary.metrics,
            "best_total_reward": str(summary.best_total_reward),
        },
        eligibility_status="pending_review",
    )


def evaluate_static_policy_walk_forward(
    run: SimulationRun,
    training_candles: Sequence[Candle],
    validation_candles: Sequence[Candle],
    test_candles: Sequence[Candle],
    events: Sequence[MarketEvent] | None = None,
    candidate_action_ids: Sequence[int] | None = None,
) -> RlWalkForwardEvaluation:
    """Evaluate a static policy across train, validation, and test windows.

    Args:
        run: Simulation run used as immutable account context.
        training_candles: Training window candles used for action selection.
        validation_candles: Validation window candles for out-of-sample scoring.
        test_candles: Test window candles for final out-of-sample scoring.
        events: Optional market events available to observations.
        candidate_action_ids: Optional candidate discrete actions.

    Returns:
        Walk-forward evaluation summary.

    Raises:
        ValueError: If validation or test windows are empty.
    """

    if len(validation_candles) == 0:
        raise ValueError("Walk-forward evaluation requires validation candles.")
    if len(test_candles) == 0:
        raise ValueError("Walk-forward evaluation requires test candles.")
    training_summary = train_static_policy(
        run=run,
        candles=training_candles,
        events=events,
        candidate_action_ids=candidate_action_ids,
    )
    selected_action_id = training_summary.best_action_id
    selected_target_weight = ACTION_TARGET_WEIGHTS.get(
        selected_action_id,
        Decimal("0"),
    )
    validation_total_reward = _evaluate_static_action(
        run,
        validation_candles,
        events,
        selected_action_id,
    )
    test_total_reward = _evaluate_static_action(
        run,
        test_candles,
        events,
        selected_action_id,
    )
    return RlWalkForwardEvaluation(
        algorithm="static_discrete_policy_walk_forward",
        selected_action_id=selected_action_id,
        selected_target_weight=selected_target_weight,
        training_summary=training_summary,
        validation_total_reward=validation_total_reward,
        test_total_reward=test_total_reward,
        metrics={
            "training_candle_count": len(training_candles),
            "validation_candle_count": len(validation_candles),
            "test_candle_count": len(test_candles),
            "training_best_total_reward": str(training_summary.best_total_reward),
            "validation_total_reward": str(validation_total_reward),
            "test_total_reward": str(test_total_reward),
        },
    )


def _evaluate_static_action(
    run: SimulationRun,
    candles: Sequence[Candle],
    events: Sequence[MarketEvent] | None,
    action_id: int,
) -> Decimal:
    """Evaluate one static action over a full environment episode.

    Args:
        run: Simulation run used as immutable account context.
        candles: Ordered point-in-time candles.
        events: Optional market events available to observations.
        action_id: Candidate action identifier.

    Returns:
        Cumulative episode reward.
    """

    environment = TradingEnvironment(run, candles, events)
    environment.reset()
    total_reward = Decimal("0")
    while True:
        step = environment.step(RlAction(action_id=action_id))
        total_reward += step.reward
        if step.done:
            return total_reward
