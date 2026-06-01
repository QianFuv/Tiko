"""Deterministic rule-based trading agent."""

from decimal import Decimal
from typing import Literal
from uuid import uuid4

from tiko.domain.decision import TradeIntent
from tiko.domain.market import Candle, MarketEvent
from tiko.domain.observation import Observation

DecisionAction = Literal["open_long", "open_short", "hold"]


class RuleBasedTraderAgent:
    """Create structured intent from simple candle direction rules."""

    def __init__(
        self,
        agent_id: str = "rule_based_trader",
        target_weight: Decimal = Decimal("0.10"),
        confidence: float = 0.7,
    ) -> None:
        """Initialize the rule-based agent.

        Args:
            agent_id: Stable agent identifier.
            target_weight: Absolute target weight for directional signals.
            confidence: Confidence assigned to directional signals.
        """

        self.agent_id = agent_id
        self._target_weight = target_weight
        self._confidence = confidence

    def decide(self, observation: Observation) -> TradeIntent:
        """Create structured trade intent from an observation.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            Structured trade intent.
        """

        action, target_weight, confidence = self._select_action(observation)
        return TradeIntent(
            decision_id=uuid4(),
            run_id=observation.run_id,
            observation_id=observation.observation_id,
            input_data_as_of=observation.as_of,
            agent_id=self.agent_id,
            symbol=observation.symbol,
            market_type="synthetic",
            action=action,
            target_weight=target_weight,
            max_leverage=Decimal("1"),
            confidence=confidence,
            expected_holding_period="1h",
            thesis=self._create_thesis(action),
            evidence=self._create_evidence(observation),
            invalidation_conditions=["price_direction_reverses"],
            data_quality_score=(
                observation.data_quality.score if observation.candles else 0.0
            ),
            created_at_sim_time=observation.as_of,
        )

    def _select_action(
        self, observation: Observation
    ) -> tuple[DecisionAction, Decimal, float]:
        """Select action, target weight, and confidence.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            Action, target weight, and confidence.
        """

        if not observation.candles:
            return "hold", Decimal("0"), 0.5
        first_price, latest_price = self._select_reference_prices(observation.candles)
        if latest_price > first_price:
            return "open_long", self._target_weight, self._confidence
        if latest_price < first_price:
            return "open_short", -self._target_weight, self._confidence
        return "hold", Decimal("0"), 0.5

    def _select_reference_prices(
        self, candles: list[Candle]
    ) -> tuple[Decimal, Decimal]:
        """Select comparison prices for a directional rule.

        Args:
            candles: Point-in-time candles in the observation.

        Returns:
            First and latest prices to compare.
        """

        if len(candles) == 1:
            candle = candles[0]
            return candle.open, candle.close
        return candles[0].close, candles[-1].close

    def _create_thesis(self, action: DecisionAction) -> str:
        """Create a short thesis string for the selected action.

        Args:
            action: Selected action.

        Returns:
            Thesis text.
        """

        if action == "open_long":
            return "Recent point-in-time candles show upward direction."
        if action == "open_short":
            return "Recent point-in-time candles show downward direction."
        return "No directional candle edge is available."

    def _create_evidence(self, observation: Observation) -> list[dict[str, object]]:
        """Create structured evidence for the selected observation.

        Args:
            observation: Source observation.

        Returns:
            Evidence records.
        """

        if not observation.candles:
            return [{"type": "candle_count", "value": 0}]
        evidence: list[dict[str, object]] = [
            {"type": "candle_count", "value": len(observation.candles)},
            {"type": "first_close", "value": str(observation.candles[0].close)},
            {"type": "latest_close", "value": str(observation.candles[-1].close)},
        ]
        evidence.extend(self._create_event_evidence(observation.events))
        return evidence

    def _create_event_evidence(
        self, events: list[MarketEvent]
    ) -> list[dict[str, object]]:
        """Create point-in-time market event evidence.

        Args:
            events: Market events included in the observation.

        Returns:
            Evidence records for non-candle events.
        """

        return [
            {
                "type": "market_event",
                "event_type": event.type,
                "source": event.source,
                "confidence": event.confidence,
                "simulated_time": event.simulated_time.isoformat(),
                "payload": dict(event.payload),
            }
            for event in events
            if event.type != "candle_closed"
        ]
