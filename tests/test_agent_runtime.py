"""Tests for structured agent runtime behavior."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from tiko.agents import (
    AgentRuntime,
    AgentRuntimeError,
    OpenRouterAgentError,
    OpenRouterClient,
    OpenRouterTraderAgent,
    RuleBasedTraderAgent,
)
from tiko.domain.account import SimAccount
from tiko.domain.decision import TradeIntent
from tiko.domain.market import Candle
from tiko.domain.observation import Observation


def create_account() -> SimAccount:
    """Create a simulated account for agent tests.

    Returns:
        Simulated account domain model.
    """

    return SimAccount(
        account_id=uuid4(),
        name="agent-account",
        initial_equity=Decimal("1000"),
        cash_balance=Decimal("1000"),
        total_equity=Decimal("1000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        status="active",
    )


def create_candle(close: Decimal, hour: int) -> Candle:
    """Create a candle for agent tests.

    Args:
        close: Candle close price.
        hour: Candle close hour.

    Returns:
        Candle domain model.
    """

    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=datetime(2026, 1, 1, hour - 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, hour, tzinfo=UTC),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1"),
        quote_volume=None,
        source="test",
        as_of=datetime(2026, 1, 1, hour, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, hour, tzinfo=UTC),
    )


def create_observation(candles: list[Candle]) -> Observation:
    """Create an observation for agent tests.

    Args:
        candles: Candles included in the observation.

    Returns:
        Observation domain model.
    """

    return Observation(
        observation_id=uuid4(),
        run_id=uuid4(),
        symbol="BTCUSDT",
        as_of=datetime(2026, 1, 1, 2, tzinfo=UTC),
        account=create_account(),
        candles=candles,
        events=[],
    )


class WrongSymbolAgent:
    """Agent that intentionally returns an invalid symbol."""

    agent_id = "wrong_symbol"

    def decide(self, observation: Observation) -> TradeIntent:
        """Return an intent that violates observation scope.

        Args:
            observation: Source observation.

        Returns:
            Invalid trade intent.
        """

        return TradeIntent(
            decision_id=uuid4(),
            run_id=observation.run_id,
            agent_id=self.agent_id,
            symbol="ETHUSDT",
            market_type="synthetic",
            action="hold",
            target_weight=Decimal("0"),
            max_leverage=Decimal("1"),
            confidence=0.5,
            expected_holding_period="1h",
            thesis="Invalid scope.",
            evidence=[],
            invalidation_conditions=[],
            data_quality_score=0.0,
            created_at_sim_time=observation.as_of,
        )


def test_rule_agent_returns_hold_without_candles() -> None:
    """Verify empty observations produce non-executable hold intent."""

    intent = AgentRuntime(RuleBasedTraderAgent()).evaluate(create_observation([]))

    assert intent.action == "hold"
    assert intent.target_weight == Decimal("0")
    assert intent.data_quality_score == 0.0


def test_rule_agent_returns_long_for_rising_candles() -> None:
    """Verify rising point-in-time candles produce long intent."""

    observation = create_observation(
        [create_candle(Decimal("100"), 1), create_candle(Decimal("110"), 2)]
    )

    intent = AgentRuntime(RuleBasedTraderAgent()).evaluate(observation)

    assert intent.action == "open_long"
    assert intent.target_weight == Decimal("0.10")
    assert intent.symbol == observation.symbol
    assert intent.run_id == observation.run_id


def test_rule_agent_returns_short_for_falling_candles() -> None:
    """Verify falling point-in-time candles produce short intent."""

    observation = create_observation(
        [create_candle(Decimal("110"), 1), create_candle(Decimal("100"), 2)]
    )

    intent = AgentRuntime(RuleBasedTraderAgent()).evaluate(observation)

    assert intent.action == "open_short"
    assert intent.target_weight == Decimal("-0.10")


def test_agent_runtime_rejects_scope_mismatch() -> None:
    """Verify runtime rejects agent output outside observation scope."""

    with pytest.raises(AgentRuntimeError, match="symbol"):
        AgentRuntime(WrongSymbolAgent()).evaluate(create_observation([]))


def test_openrouter_agent_builds_scoped_trade_intent() -> None:
    """Verify OpenRouter proposals are converted into scoped trade intent."""

    observation = create_observation(
        [create_candle(Decimal("100"), 1), create_candle(Decimal("105"), 2)]
    )
    captured_payload: dict[str, object] = {}

    def transport(
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """Return a fake OpenRouter structured response."""

        captured_payload["endpoint"] = endpoint
        captured_payload["headers"] = headers
        captured_payload["payload"] = payload
        captured_payload["timeout_seconds"] = timeout_seconds
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "run_id": str(uuid4()),
                                "symbol": "ETHUSDT",
                                "action": "open_long",
                                "target_weight": "0.12",
                                "max_leverage": "1",
                                "confidence": 0.67,
                                "expected_holding_period": "1h",
                                "thesis": "Point-in-time candles are rising.",
                                "evidence": [{"type": "candle_direction"}],
                                "invalidation_conditions": ["trend_reverses"],
                                "data_quality_score": 1.0,
                            }
                        )
                    }
                }
            ]
        }

    client = OpenRouterClient(api_key="test-key", transport=transport)
    intent = AgentRuntime(OpenRouterTraderAgent(client)).evaluate(observation)

    request_payload = captured_payload["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["model"] == "openrouter/free"
    assert "response_format" in request_payload
    assert intent.run_id == observation.run_id
    assert intent.symbol == observation.symbol
    assert intent.action == "open_long"
    assert intent.target_weight == Decimal("0.12")
    assert intent.confidence == 0.67


def test_openrouter_agent_rejects_malformed_response() -> None:
    """Verify malformed provider responses fail before intent validation."""

    def transport(
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """Return an invalid OpenRouter message payload."""

        return {"choices": [{"message": {"content": "not-json"}}]}

    client = OpenRouterClient(api_key="test-key", transport=transport)

    with pytest.raises(OpenRouterAgentError, match="valid JSON"):
        OpenRouterTraderAgent(client).decide(create_observation([]))


def test_openrouter_agent_rejects_invalid_decimal_response_fields() -> None:
    """Verify invalid decimal proposal fields fail as provider errors."""

    def transport(
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """Return a response with invalid decimal content."""

        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "hold",
                                "target_weight": "0",
                                "max_leverage": "not-a-decimal",
                                "confidence": 0.5,
                                "expected_holding_period": "1h",
                                "thesis": "No edge.",
                                "evidence": [],
                                "invalidation_conditions": [],
                                "data_quality_score": 0.5,
                            }
                        )
                    }
                }
            ]
        }

    client = OpenRouterClient(api_key="test-key", transport=transport)

    with pytest.raises(OpenRouterAgentError, match="max_leverage"):
        OpenRouterTraderAgent(client).decide(create_observation([]))


def test_openrouter_client_falls_back_to_json_object_mode() -> None:
    """Verify provider schema-mode failures can fall back to JSON object mode."""

    response_format_types: list[str] = []

    def transport(
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """Fail the first request and accept the JSON object retry."""

        response_format = payload["response_format"]
        assert isinstance(response_format, dict)
        response_format_type = response_format["type"]
        assert isinstance(response_format_type, str)
        response_format_types.append(response_format_type)
        if response_format_type == "json_schema":
            return {"error": {"message": "Provider returned error"}}
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "hold",
                                "target_weight": "0",
                                "max_leverage": "1",
                                "confidence": 0.5,
                                "expected_holding_period": "1h",
                                "thesis": "No edge.",
                                "evidence": [],
                                "invalidation_conditions": [],
                                "data_quality_score": 0.5,
                            }
                        )
                    }
                }
            ]
        }

    client = OpenRouterClient(api_key="test-key", transport=transport)
    intent = OpenRouterTraderAgent(client).decide(create_observation([]))

    assert response_format_types == ["json_schema", "json_object"]
    assert intent.action == "hold"
