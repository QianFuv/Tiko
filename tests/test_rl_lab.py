"""Tests for advisory RL lab utilities."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from tiko.domain import RlAction, SimAccount, SimulationRun
from tiko.domain.market import Candle
from tiko.rl_lab import (
    TradingEnvironment,
    build_reward_components,
    calculate_reward,
    train_static_policy,
)


def create_run() -> SimulationRun:
    """Create a simulation run fixture for RL environment tests.

    Returns:
        Simulation run fixture.
    """

    account = SimAccount(
        account_id=uuid4(),
        name="rl-account",
        initial_equity=Decimal("100000"),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
    )
    return SimulationRun(
        run_id=uuid4(),
        name="rl-run",
        status="created",
        mode="historical_replay",
        account=account,
        symbols=["BTCUSDT"],
        start_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        current_sim_time=datetime(2026, 1, 1, tzinfo=UTC),
        config={},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_candles() -> list[Candle]:
    """Create point-in-time candles for RL environment tests.

    Returns:
        Ordered candle fixtures.
    """

    first_time = datetime(2026, 1, 1, 1, tzinfo=UTC)
    second_time = first_time + timedelta(hours=1)
    return [
        Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=first_time - timedelta(hours=1),
            close_time=first_time,
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("100"),
            volume=Decimal("10"),
            source="rl-test",
            as_of=first_time,
            created_at=first_time,
        ),
        Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=first_time,
            close_time=second_time,
            open=Decimal("100"),
            high=Decimal("112"),
            low=Decimal("99"),
            close=Decimal("110"),
            volume=Decimal("12"),
            source="rl-test",
            as_of=second_time,
            created_at=second_time,
        ),
    ]


def test_trading_environment_reset_and_step_are_advisory() -> None:
    """Verify environment steps return observations and no execution artifacts."""

    environment = TradingEnvironment(create_run(), create_candles())

    observation = environment.reset(seed=7)
    step = environment.step(RlAction(action_id=2))

    assert observation.symbol == "BTCUSDT"
    assert len(observation.candles) == 1
    assert step.target_weight == Decimal("0.25")
    assert step.reward > Decimal("0")
    assert step.done is True
    assert "order" not in step.info
    assert "fill" not in step.info


def test_trading_environment_exposes_gymnasium_style_adapter() -> None:
    """Verify Gymnasium-style reset and step signatures are available."""

    environment = TradingEnvironment(create_run(), create_candles())

    observation, reset_info = environment.reset_gymnasium(
        seed=11,
        options={"episode": "smoke"},
    )
    next_observation, reward, terminated, truncated, step_info = (
        environment.step_gymnasium(2)
    )

    assert observation.symbol == "BTCUSDT"
    assert reset_info["index"] == 0
    assert reset_info["candle_count"] == 2
    assert reset_info["options"] == {"episode": "smoke"}
    assert next_observation.as_of == datetime(2026, 1, 1, 2, tzinfo=UTC)
    assert reward > 0
    assert terminated is True
    assert truncated is False
    assert step_info["target_weight"] == "0.25"
    assert step_info["invalid_action"] is False
    assert step_info["terminated"] is True
    assert step_info["truncated"] is False


def test_invalid_action_is_penalized_and_flattened() -> None:
    """Verify invalid advisory actions cannot create target exposure."""

    environment = TradingEnvironment(create_run(), create_candles())
    environment.reset()

    step = environment.step(RlAction(action_id=99))

    assert step.target_weight == Decimal("0")
    assert step.reward == Decimal("-1.0000")
    assert step.info["invalid_action"] is True


def test_reward_calculation_subtracts_all_penalties() -> None:
    """Verify reward calculation follows the architecture formula."""

    components = build_reward_components(
        previous_close=Decimal("100"),
        current_close=Decimal("110"),
        target_weight=Decimal("0.10"),
        previous_target_weight=Decimal("0"),
        is_invalid_action=False,
    )
    reward = calculate_reward(components)

    assert reward.reward == Decimal("0.009900")


def test_static_policy_training_selects_best_reward_action() -> None:
    """Verify deterministic training selects the highest reward static action."""

    summary = train_static_policy(
        run=create_run(),
        candles=create_candles(),
        candidate_action_ids=[0, 1, 2, 3],
    )

    assert summary.algorithm == "static_discrete_policy_search"
    assert summary.episode_count == 4
    assert summary.best_action_id == 3
    assert summary.best_total_reward == summary.action_rewards[3]
    assert summary.action_rewards[3] > summary.action_rewards[0]
    assert summary.metrics["best_target_weight"] == "0.50"


def test_static_policy_training_penalizes_invalid_action_candidates() -> None:
    """Verify invalid action candidates cannot beat valid positive-reward actions."""

    summary = train_static_policy(
        run=create_run(),
        candles=create_candles(),
        candidate_action_ids=[3, 99],
    )

    assert summary.best_action_id == 3
    assert summary.action_rewards[99] < Decimal("0")


def test_static_policy_training_requires_candidate_actions() -> None:
    """Verify static policy training rejects empty candidate lists."""

    with pytest.raises(ValueError, match="at least one action"):
        train_static_policy(
            run=create_run(),
            candles=create_candles(),
            candidate_action_ids=[],
        )
