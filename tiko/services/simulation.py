"""In-memory simulation orchestration service."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tiko.core.config import Settings
from tiko.db.repositories import SimulationRepository
from tiko.domain.account import SimAccount
from tiko.domain.decision import TradeIntent
from tiko.domain.market import Candle, MarketEvent
from tiko.domain.order import Fill, SimOrder
from tiko.domain.risk import RiskReview
from tiko.domain.simulation import SimulationRun
from tiko.services.portfolio import PortfolioService
from tiko.services.risk import RiskService
from tiko.simulation.broker import SimBroker
from tiko.simulation.clock import advance_simulated_time
from tiko.simulation.event_bus import EventBus
from tiko.simulation.ledger import apply_fill_to_account
from tiko.simulation.replay import MarketReplay, MarketReplayExhausted
from tiko.simulation.state import SimulationState, SimulationStepResult
from tiko.simulation.synthetic import generate_synthetic_candle


class SimulationService:
    """Coordinate deterministic simulation runs with optional persistence."""

    def __init__(
        self, settings: Settings, repository: SimulationRepository | None = None
    ) -> None:
        """Initialize service dependencies and state.

        Args:
            settings: Application settings.
            repository: Optional persistence repository.
        """

        self._settings = settings
        self._repository = repository
        self._states: dict[UUID, SimulationState] = {}
        self._risk_service = RiskService(settings.minimum_trade_confidence)
        self._portfolio_service = PortfolioService()
        self._broker = SimBroker()
        self._event_bus = EventBus()

    def create_run(
        self,
        name: str,
        symbols: list[str],
        start_sim_time: datetime | None = None,
        replay_candles: Sequence[Candle] | None = None,
    ) -> SimulationRun:
        """Create a new process-local simulation run.

        Args:
            name: Human-readable run name.
            symbols: Symbols included in the simulation.
            start_sim_time: Optional start time. Defaults to current UTC hour.
            replay_candles: Optional normalized candles for historical replay.

        Returns:
            Created simulation run.
        """

        run_id = uuid4()
        market_replay = (
            MarketReplay(replay_candles, symbols)
            if replay_candles is not None
            else None
        )
        account = SimAccount(
            account_id=uuid4(),
            name=f"{name}-account",
            initial_equity=Decimal(self._settings.default_initial_equity),
            cash_balance=Decimal(self._settings.default_initial_equity),
            total_equity=Decimal(self._settings.default_initial_equity),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            max_drawdown=Decimal("0"),
            status="active",
        )
        if start_sim_time is not None:
            start_time = start_sim_time
        elif market_replay is not None:
            start_time = market_replay.start_time()
        else:
            start_time = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        run = SimulationRun(
            run_id=run_id,
            name=name,
            status="created",
            mode="historical_replay"
            if market_replay is not None
            else "synthetic_market",
            account=account,
            symbols=symbols,
            start_sim_time=start_time,
            current_sim_time=start_time,
            config={
                "data_source": "replay" if market_replay is not None else "synthetic"
            },
            created_at=datetime.now(UTC),
        )
        self._states[run_id] = SimulationState(run=run, market_replay=market_replay)
        if self._repository is not None:
            self._repository.save_run(run)
        return run

    def list_runs(self) -> list[SimulationRun]:
        """List all process-local simulation runs.

        Returns:
            Simulation runs in insertion order.
        """

        return [state.run for state in self._states.values()]

    def get_run(self, run_id: UUID) -> SimulationRun:
        """Get one simulation run by ID.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Simulation run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return self._states[run_id].run

    def step_run(self, run_id: UUID, confidence: float = 0.7) -> SimulationStepResult:
        """Advance a simulation run by one deterministic synthetic candle.

        Args:
            run_id: Simulation run identifier.
            confidence: Synthetic agent confidence for the generated intent.

        Returns:
            Step result with generated decision, risk, order, and fill artifacts.
        """

        state = self._states[run_id]
        try:
            candle = self._next_candle(state)
        except MarketReplayExhausted:
            completed_run = state.run.model_copy(update={"status": "completed"})
            state.run = completed_run
            if self._repository is not None:
                self._repository.save_run(completed_run)
            raise
        next_time = candle.as_of
        symbol = candle.symbol
        event = MarketEvent(
            event_id=uuid4(),
            type="candle_closed",
            symbol=symbol,
            simulated_time=next_time,
            payload={"close": str(candle.close), "source": candle.source},
            source="synthetic",
            confidence=1.0,
        )
        self._event_bus.publish(event)
        intent = self._create_trade_intent(
            run_id=run_id,
            symbol=symbol,
            confidence=confidence,
            simulated_time=next_time,
        )
        risk_review = self._risk_service.review(intent)
        order = None
        fill = None
        order_request = self._portfolio_service.create_order_request(
            account=state.run.account,
            intent=intent,
            risk_review=risk_review,
            reference_price=candle.close,
        )
        account = state.run.account
        if order_request is not None:
            order, fill = self._broker.submit_market_order(order_request, candle.close)
            account = apply_fill_to_account(account, fill)
            state.orders.append(order)
            state.fills.append(fill)
        updated_run = state.run.model_copy(
            update={
                "status": "running",
                "current_sim_time": next_time,
                "account": account,
            }
        )
        state.run = updated_run
        state.step_index += 1
        state.candles.append(candle)
        state.events.append(event)
        state.decisions.append(intent)
        state.risk_reviews.append(risk_review)
        result = SimulationStepResult(
            run=updated_run,
            candle=candle,
            event=event,
            decision=intent,
            risk_review=risk_review,
            order=order,
            fill=fill,
        )
        if self._repository is not None:
            self._repository.save_step_result(result)
        return result

    def _next_candle(self, state: SimulationState) -> Candle:
        """Return the next candle for a simulation state.

        Args:
            state: Simulation state to advance.

        Returns:
            Next candle from replay or synthetic generation.

        Raises:
            MarketReplayExhausted: If replay mode has no remaining candles.
        """

        if state.market_replay is not None:
            return state.market_replay.next_candle()
        next_time = advance_simulated_time(state.run.current_sim_time, 3600)
        return generate_synthetic_candle(
            state.run.symbols[0], state.step_index, next_time
        )

    def list_orders(self) -> list[SimOrder]:
        """List simulated orders across all runs.

        Returns:
            Simulated orders.
        """

        return [order for state in self._states.values() for order in state.orders]

    def list_fills(self) -> list[Fill]:
        """List simulated fills across all runs.

        Returns:
            Simulated fills.
        """

        return [fill for state in self._states.values() for fill in state.fills]

    def list_decisions(self) -> list[TradeIntent]:
        """List generated trade intents across all runs.

        Returns:
            Structured trade intents.
        """

        return [
            decision for state in self._states.values() for decision in state.decisions
        ]

    def get_latest_risk_review(self, run_id: UUID) -> RiskReview | None:
        """Return the latest risk review for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Latest risk review or `None`.
        """

        reviews = self._states[run_id].risk_reviews
        return reviews[-1] if reviews else None

    def _create_trade_intent(
        self,
        run_id: UUID,
        symbol: str,
        confidence: float,
        simulated_time: datetime,
    ) -> TradeIntent:
        """Create deterministic synthetic trade intent for a step.

        Args:
            run_id: Simulation run identifier.
            symbol: Symbol for the intent.
            confidence: Synthetic confidence score.
            simulated_time: Simulated decision time.

        Returns:
            Structured trade intent.
        """

        return TradeIntent(
            decision_id=uuid4(),
            run_id=run_id,
            agent_id="synthetic_trader",
            symbol=symbol,
            market_type="synthetic",
            action="open_long",
            target_weight=Decimal("0.10"),
            max_leverage=Decimal("1"),
            confidence=confidence,
            expected_holding_period="1h",
            thesis="Synthetic trend-following seed decision.",
            evidence=[{"type": "synthetic_candle"}],
            invalidation_conditions=["confidence_below_threshold"],
            data_quality_score=1.0,
            created_at_sim_time=simulated_time,
        )
