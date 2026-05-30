"""Runtime validation for structured trading agents."""

from typing import Protocol

from tiko.domain.decision import TradeIntent
from tiko.domain.observation import Observation


class AgentRuntimeError(ValueError):
    """Raised when an agent output violates runtime boundaries."""


class TradingAgent(Protocol):
    """Define the minimal structured trading agent interface."""

    agent_id: str

    def decide(self, observation: Observation) -> TradeIntent:
        """Create a structured trade intent from an observation.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            Structured trade intent.
        """


class AgentRuntime:
    """Evaluate one trading agent and validate its structured output."""

    def __init__(self, agent: TradingAgent) -> None:
        """Initialize the runtime.

        Args:
            agent: Trading agent implementation.
        """

        self._agent = agent

    def evaluate(self, observation: Observation) -> TradeIntent:
        """Evaluate an agent against an observation.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            Validated trade intent.

        Raises:
            AgentRuntimeError: If the agent output does not match observation scope.
        """

        intent = self._agent.decide(observation)
        if not isinstance(intent, TradeIntent):
            raise AgentRuntimeError("Agent output must be a TradeIntent instance.")
        self._validate_scope(observation, intent)
        return intent

    def _validate_scope(self, observation: Observation, intent: TradeIntent) -> None:
        """Validate intent scope against the source observation.

        Args:
            observation: Source observation.
            intent: Agent trade intent.

        Raises:
            AgentRuntimeError: If run ID or symbol do not match.
        """

        if intent.run_id != observation.run_id:
            raise AgentRuntimeError("Agent intent run_id does not match observation.")
        if intent.symbol != observation.symbol:
            raise AgentRuntimeError("Agent intent symbol does not match observation.")
