"""In-memory simulation orchestration service."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from tiko.agents import AgentRuntime, RuleBasedTraderAgent
from tiko.analysis import build_run_benchmark, compare_run_benchmarks
from tiko.core.config import Settings
from tiko.db.repositories import SimulationRepository
from tiko.domain.account import (
    LedgerEntry,
    MetricSnapshot,
    PortfolioSnapshot,
    Position,
    SimAccount,
)
from tiko.domain.agent import AgentMessage, AgentMessageRole, AgentRun, DecisionTrace
from tiko.domain.comparison import RunBenchmark, RunComparison
from tiko.domain.decision import DecisionReview, TradeIntent
from tiko.domain.market import Candle, FeatureSnapshot, MarketEvent, OrderBookSnapshot
from tiko.domain.memory import MemoryEntry, MemoryType
from tiko.domain.observation import Observation
from tiko.domain.order import Fill, SimOrder
from tiko.domain.reporting import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertStatus,
    ReportArtifact,
)
from tiko.domain.risk import RiskLimits, RiskReview
from tiko.domain.simulation import SimulationRun
from tiko.observation import ObservationBuilder
from tiko.services.portfolio import PortfolioService
from tiko.services.risk import RiskService
from tiko.simulation.broker import SimBroker
from tiko.simulation.clock import advance_simulated_time
from tiko.simulation.event_bus import EventBus
from tiko.simulation.ledger import LedgerUpdate, apply_fill_to_ledger
from tiko.simulation.metrics import MetricsEngine
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
        self._portfolio_service = PortfolioService()
        self._broker = SimBroker()
        self._event_bus = EventBus()
        self._observation_builder = ObservationBuilder()
        self._metrics_engine = MetricsEngine()

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
        self._states[run_id] = SimulationState(
            run=run,
            risk_limits=self._build_default_risk_limits(run_id),
            market_replay=market_replay,
        )
        if self._repository is not None:
            self._repository.save_run(run)
        return run

    def list_runs(self) -> list[SimulationRun]:
        """List all process-local simulation runs.

        Returns:
            Simulation runs in insertion order.
        """

        if self._repository is not None:
            return self._repository.list_runs()
        return [state.run for state in self._states.values()]

    def get_risk_limits(self, run_id: UUID) -> RiskLimits:
        """Return active risk limits for a simulation run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Active run-level risk limits.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return self._get_state(run_id).risk_limits

    def update_risk_limits(
        self,
        run_id: UUID,
        minimum_confidence: float,
        minimum_data_quality_score: float,
        max_target_weight: Decimal,
        max_order_notional: Decimal,
    ) -> RiskLimits:
        """Update active risk limits for future simulation steps.

        Args:
            run_id: Simulation run identifier.
            minimum_confidence: Minimum confidence required for approval.
            minimum_data_quality_score: Minimum observation quality required.
            max_target_weight: Maximum absolute target portfolio weight.
            max_order_notional: Maximum simulated order notional.

        Returns:
            Updated run-level risk limits.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        limits = RiskLimits(
            run_id=run_id,
            minimum_confidence=minimum_confidence,
            minimum_data_quality_score=minimum_data_quality_score,
            max_target_weight=max_target_weight,
            max_order_notional=max_order_notional,
            live_trading_allowed=False,
        )
        state.risk_limits = limits
        return limits

    def _build_default_risk_limits(self, run_id: UUID) -> RiskLimits:
        """Build risk limits from application settings for one run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Default risk limits with live trading disabled.
        """

        return RiskLimits(
            run_id=run_id,
            minimum_confidence=self._settings.minimum_trade_confidence,
            minimum_data_quality_score=self._settings.minimum_data_quality_score,
            max_target_weight=self._settings.max_target_weight,
            max_order_notional=self._settings.max_order_notional,
            live_trading_allowed=False,
        )

    def _build_risk_service(self, limits: RiskLimits) -> RiskService:
        """Build a risk service from run-level limits.

        Args:
            limits: Active risk limits.

        Returns:
            Configured risk service.
        """

        return RiskService(
            minimum_confidence=limits.minimum_confidence,
            minimum_data_quality_score=limits.minimum_data_quality_score,
            max_target_weight=limits.max_target_weight,
            max_order_notional=limits.max_order_notional,
        )

    def _get_state(self, run_id: UUID) -> SimulationState:
        """Return process-local state, hydrating persisted artifacts if needed.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Simulation state for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._states.get(run_id)
        if state is not None:
            return state
        if self._repository is None:
            raise KeyError(run_id)

        run = self._repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        agent_runs = self._repository.list_agent_runs(run_id)
        agent_messages = [
            message
            for agent_run in agent_runs
            for message in self._repository.list_agent_messages(agent_run.agent_run_id)
        ]
        decisions = self._repository.list_decisions(run_id)
        candles = self._repository.list_candles(run_id)
        hydrated_state = SimulationState(
            run=run,
            risk_limits=self._build_default_risk_limits(run_id),
            step_index=len(candles),
            candles=candles,
            orderbook_snapshots=self._repository.list_orderbook_snapshots(run_id),
            feature_snapshots=self._repository.list_feature_snapshots(run_id),
            events=self._repository.list_market_events(run_id),
            observations=self._repository.list_observation_snapshots(run_id),
            agent_runs=agent_runs,
            agent_messages=agent_messages,
            decisions=decisions,
            decision_reviews=[
                review
                for decision in decisions
                for review in self._repository.list_decision_reviews(
                    decision.decision_id
                )
            ],
            memory_entries=self._repository.list_memory_entries(run_id),
            reports=self._repository.list_reports(run_id),
            alerts=self._repository.list_alerts(run_id),
            risk_reviews=self._repository.list_risk_reviews(run_id),
            orders=self._repository.list_orders(run_id),
            fills=self._repository.list_fills(run_id),
            positions=self._repository.list_positions(run_id),
            ledger_entries=self._repository.list_ledger_entries(run_id),
            portfolio_snapshots=self._repository.list_portfolio_snapshots(run_id),
            metric_snapshots=self._repository.list_metric_snapshots(run_id),
        )
        self._states[run_id] = hydrated_state
        return hydrated_state

    def _list_states(self) -> list[SimulationState]:
        """List process-local or hydrated states in run creation order.

        Returns:
            Simulation states.
        """

        if self._repository is None:
            return list(self._states.values())
        return [self._get_state(run.run_id) for run in self._repository.list_runs()]

    def get_run(self, run_id: UUID) -> SimulationRun:
        """Get one simulation run by ID.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Simulation run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return self._get_state(run_id).run

    def update_run_status(
        self,
        run_id: UUID,
        status: Literal["created", "running", "paused", "stopped", "completed"],
    ) -> SimulationRun:
        """Update one simulation run lifecycle status.

        Args:
            run_id: Simulation run identifier.
            status: New lifecycle status.

        Returns:
            Updated simulation run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        account_status = {
            "created": "active",
            "running": "active",
            "paused": "paused",
            "stopped": "stopped",
            "completed": state.run.account.status,
        }[status]
        account = state.run.account.model_copy(update={"status": account_status})
        updates: dict[str, object] = {"status": status, "account": account}
        if status == "stopped":
            updates["end_sim_time"] = state.run.current_sim_time
        updated_run = state.run.model_copy(update=updates)
        state.run = updated_run
        if self._repository is not None:
            self._repository.save_run(updated_run)
        return updated_run

    def update_run_speed(
        self, run_id: UUID, speed_multiplier: Decimal
    ) -> SimulationRun:
        """Update one simulation run speed multiplier.

        Args:
            run_id: Simulation run identifier.
            speed_multiplier: Positive simulation speed multiplier.

        Returns:
            Updated simulation run.

        Raises:
            KeyError: If no run exists for the ID.
            ValueError: If the multiplier is not positive.
        """

        if speed_multiplier <= Decimal("0"):
            raise ValueError("Simulation speed multiplier must be positive.")
        state = self._get_state(run_id)
        updated_run = state.run.model_copy(
            update={"speed_multiplier": speed_multiplier}
        )
        state.run = updated_run
        if self._repository is not None:
            self._repository.save_run(updated_run)
        return updated_run

    def step_run(self, run_id: UUID, confidence: float = 0.7) -> SimulationStepResult:
        """Advance a simulation run by one deterministic synthetic candle.

        Args:
            run_id: Simulation run identifier.
            confidence: Synthetic agent confidence for the generated intent.

        Returns:
            Step result with generated decision, risk, order, and fill artifacts.
        """

        state = self._get_state(run_id)
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
        previous_candle = state.candles[-1] if state.candles else None
        orderbook_snapshot = self._build_orderbook_snapshot(candle)
        feature_snapshot = self._build_feature_snapshot(
            run_id, candle, previous_candle, event.event_id
        )
        self._event_bus.publish(event)
        decision_run = state.run.model_copy(
            update={
                "status": "running",
                "current_sim_time": next_time,
            }
        )
        state.candles.append(candle)
        state.orderbook_snapshots.append(orderbook_snapshot)
        state.feature_snapshots.append(feature_snapshot)
        state.events.append(event)
        observation = self._observation_builder.build(
            run=decision_run,
            symbol=symbol,
            as_of=next_time,
            candles=state.candles,
            events=state.events,
            orderbooks=state.orderbook_snapshots,
            feature_snapshots=state.feature_snapshots,
            positions=state.positions,
            risk_limits=state.risk_limits,
            memory_entries=state.memory_entries,
            observation_id=uuid5(NAMESPACE_URL, f"observation:{event.event_id}"),
        )
        intent = self._create_trade_intent(
            run_id=run_id,
            symbol=symbol,
            confidence=confidence,
            simulated_time=next_time,
        )
        risk_review = self._build_risk_service(state.risk_limits).review(intent)
        order = None
        fill = None
        order_request = self._portfolio_service.create_order_request(
            account=decision_run.account,
            intent=intent,
            risk_review=risk_review,
            reference_price=candle.close,
        )
        account = decision_run.account
        ledger_update: LedgerUpdate | None = None
        if order_request is not None:
            order, fill = self._broker.submit_market_order(order_request, candle.close)
            ledger_update = apply_fill_to_ledger(account, fill)
            account = ledger_update.account
            state.orders.append(order)
            state.fills.append(fill)
        updated_run = decision_run.model_copy(update={"account": account})
        state.run = updated_run
        state.step_index += 1
        agent_run = self._build_agent_run(intent)
        agent_messages = tuple(self._build_agent_messages(agent_run, intent))
        state.observations.append(observation)
        state.agent_runs.append(agent_run)
        state.agent_messages.extend(agent_messages)
        state.decisions.append(intent)
        state.risk_reviews.append(risk_review)
        positions = tuple(self._derive_positions(state))
        state.positions = list(positions)
        ledger_entry = (
            self._build_ledger_entry(updated_run, fill, ledger_update)
            if fill is not None and ledger_update is not None
            else None
        )
        if ledger_entry is not None:
            state.ledger_entries.append(ledger_entry)
        portfolio_snapshot = self._build_portfolio_snapshot(
            updated_run, positions, event.event_id
        )
        metric_snapshot = self._build_metric_snapshot(
            updated_run, state.orders, state.fills, event.event_id
        )
        state.portfolio_snapshots.append(portfolio_snapshot)
        state.metric_snapshots.append(metric_snapshot)
        result = SimulationStepResult(
            run=updated_run,
            candle=candle,
            orderbook_snapshot=orderbook_snapshot,
            feature_snapshot=feature_snapshot,
            event=event,
            observation=observation,
            agent_run=agent_run,
            agent_messages=agent_messages,
            decision=intent,
            risk_review=risk_review,
            order=order,
            fill=fill,
            positions=positions,
            ledger_entry=ledger_entry,
            portfolio_snapshot=portfolio_snapshot,
            metric_snapshot=metric_snapshot,
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

    def _build_orderbook_snapshot(self, candle: Candle) -> OrderBookSnapshot:
        """Build a synthetic order book snapshot from candle close data.

        Args:
            candle: Candle used as the point-in-time price reference.

        Returns:
            Synthetic order book snapshot.
        """

        spread_bps = Decimal("2")
        half_spread = candle.close * spread_bps / Decimal("20000")
        bid_price = candle.close - half_spread
        ask_price = candle.close + half_spread
        depth_quantity = max(candle.volume, Decimal("1"))
        return OrderBookSnapshot(
            symbol=candle.symbol,
            as_of=candle.as_of,
            bids=[(bid_price, depth_quantity)],
            asks=[(ask_price, depth_quantity)],
            mid_price=candle.close,
            spread_bps=spread_bps,
            depth_1pct_usd=candle.close * depth_quantity,
            source="synthetic_orderbook",
        )

    def _build_feature_snapshot(
        self,
        run_id: UUID,
        candle: Candle,
        previous_candle: Candle | None,
        source_event_id: UUID,
    ) -> FeatureSnapshot:
        """Build a deterministic feature snapshot from candle data.

        Args:
            run_id: Simulation run identifier.
            candle: Current candle.
            previous_candle: Previous candle for one-step return calculation.
            source_event_id: Source event identifier for deterministic snapshot IDs.

        Returns:
            Feature snapshot.
        """

        one_step_return = (
            (candle.close - previous_candle.close) / previous_candle.close
            if previous_candle is not None and previous_candle.close > Decimal("0")
            else Decimal("0")
        )
        return FeatureSnapshot(
            snapshot_id=uuid5(NAMESPACE_URL, f"feature-snapshot:{source_event_id}"),
            run_id=run_id,
            symbol=candle.symbol,
            as_of=candle.as_of,
            features={
                "close": str(candle.close),
                "volume": str(candle.volume),
                "one_step_return": str(one_step_return),
            },
            source="synthetic_feature_engine",
        )

    def list_orders(self) -> list[SimOrder]:
        """List simulated orders across all runs.

        Returns:
            Simulated orders.
        """

        if self._repository is not None:
            return self._repository.list_orders()
        return [order for state in self._list_states() for order in state.orders]

    def get_order(self, order_id: UUID) -> SimOrder:
        """Get one simulated order by ID.

        Args:
            order_id: Simulated order identifier.

        Returns:
            Simulated order.

        Raises:
            KeyError: If no order exists for the ID.
        """

        for order in self.list_orders():
            if order.order_id == order_id:
                return order
        raise KeyError(order_id)

    def list_fills(self) -> list[Fill]:
        """List simulated fills across all runs.

        Returns:
            Simulated fills.
        """

        if self._repository is not None:
            return self._repository.list_fills()
        return [fill for state in self._list_states() for fill in state.fills]

    def get_fill(self, fill_id: UUID) -> Fill:
        """Get one simulated fill by ID.

        Args:
            fill_id: Simulated fill identifier.

        Returns:
            Simulated fill.

        Raises:
            KeyError: If no fill exists for the ID.
        """

        for fill in self.list_fills():
            if fill.fill_id == fill_id:
                return fill
        raise KeyError(fill_id)

    def list_decisions(self) -> list[TradeIntent]:
        """List generated trade intents across all runs.

        Returns:
            Structured trade intents.
        """

        if self._repository is not None:
            return self._repository.list_decisions()
        return [
            decision for state in self._list_states() for decision in state.decisions
        ]

    def get_decision(self, decision_id: UUID) -> TradeIntent:
        """Get one trade intent by ID.

        Args:
            decision_id: Trade intent identifier.

        Returns:
            Trade intent.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        _state, decision = self._find_decision_state(decision_id)
        return decision

    def list_agent_runs(self) -> list[AgentRun]:
        """List agent runs for generated decisions.

        Returns:
            Agent runs generated for decisions.
        """

        stored_runs = [
            agent_run for state in self._list_states() for agent_run in state.agent_runs
        ]
        if stored_runs:
            return stored_runs
        return [
            self._build_agent_run(decision)
            for state in self._list_states()
            for decision in state.decisions
        ]

    def get_agent_run(self, agent_run_id: UUID) -> AgentRun:
        """Get one derived agent run.

        Args:
            agent_run_id: Agent run identifier.

        Returns:
            Agent run.

        Raises:
            KeyError: If no agent run exists for the ID.
        """

        for agent_run in self.list_agent_runs():
            if agent_run.agent_run_id == agent_run_id:
                return agent_run
        raise KeyError(agent_run_id)

    def list_agent_messages(self, agent_run_id: UUID) -> list[AgentMessage]:
        """List trace messages for one agent run.

        Args:
            agent_run_id: Agent run identifier.

        Returns:
            Agent messages.

        Raises:
            KeyError: If no agent run exists for the ID.
        """

        if self._repository is not None:
            messages = self._repository.list_agent_messages(agent_run_id)
            if messages:
                return messages
        for state in self._list_states():
            messages = [
                message
                for message in state.agent_messages
                if message.agent_run_id == agent_run_id
            ]
            if messages:
                return messages
        agent_run = self.get_agent_run(agent_run_id)
        decision = self.get_decision(agent_run.decision_id)
        return self._build_agent_messages(agent_run, decision)

    def replay_agent_run(self, agent_run_id: UUID) -> TradeIntent:
        """Replay a deterministic agent run against the current observation.

        Args:
            agent_run_id: Agent run identifier.

        Returns:
            Replayed structured trade intent.

        Raises:
            KeyError: If no agent run exists for the ID.
        """

        agent_run = self.get_agent_run(agent_run_id)
        decision = self.get_decision(agent_run.decision_id)
        observation = self.build_observation(decision.run_id, decision.symbol)
        return AgentRuntime(RuleBasedTraderAgent(agent_id=agent_run.agent_id)).evaluate(
            observation
        )

    def build_decision_trace(self, decision_id: UUID) -> DecisionTrace:
        """Build joined trace artifacts for one decision.

        Args:
            decision_id: Trade intent identifier.

        Returns:
            Decision trace.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        state, decision = self._find_decision_state(decision_id)
        agent_run = next(
            (
                candidate
                for candidate in state.agent_runs
                if candidate.decision_id == decision_id
            ),
            self._build_agent_run(decision),
        )
        messages = [
            message
            for message in state.agent_messages
            if message.agent_run_id == agent_run.agent_run_id
        ] or self._build_agent_messages(agent_run, decision)
        order = next(
            (
                candidate
                for candidate in state.orders
                if candidate.decision_id == decision_id
            ),
            None,
        )
        fill = (
            next(
                (
                    candidate
                    for candidate in state.fills
                    if order is not None and candidate.order_id == order.order_id
                ),
                None,
            )
            if order is not None
            else None
        )
        risk_review = next(
            (
                candidate
                for candidate in state.risk_reviews
                if candidate.decision_id == decision_id
            ),
            None,
        )
        return DecisionTrace(
            decision=decision,
            agent_run=agent_run,
            messages=messages,
            risk_review=risk_review,
            order=order,
            fill=fill,
        )

    def annotate_decision(
        self,
        decision_id: UUID,
        summary: str,
        content: dict[str, object],
        tags: list[str],
    ) -> MemoryEntry:
        """Annotate a decision by creating a decision memory entry.

        Args:
            decision_id: Trade intent identifier.
            summary: Annotation summary.
            content: Structured annotation content.
            tags: Annotation tags.

        Returns:
            Created memory entry.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        state, decision = self._find_decision_state(decision_id)
        return self.create_memory_entry(
            run_id=decision.run_id,
            memory_type="decision",
            summary=summary,
            content=content,
            tags=tags,
            available_at_sim_time=state.run.current_sim_time,
            decision_id=decision_id,
        )

    def list_events(self, run_id: UUID) -> list[MarketEvent]:
        """List market events for a simulation run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Market events for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).events)

    def list_all_events(self) -> list[MarketEvent]:
        """List market events across all simulation runs.

        Returns:
            Market events across runs.
        """

        return [event for state in self._list_states() for event in state.events]

    def list_candles(self, run_id: UUID) -> list[Candle]:
        """List candles observed by a simulation run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Candles observed by the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).candles)

    def list_orderbook_snapshots(self, run_id: UUID) -> list[OrderBookSnapshot]:
        """List order book snapshots observed by a simulation run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Order book snapshots observed by the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).orderbook_snapshots)

    def get_latest_orderbook_snapshot(
        self, symbol: str, run_id: UUID | None = None
    ) -> OrderBookSnapshot | None:
        """Return the latest order book snapshot for a symbol.

        Args:
            symbol: Market symbol.
            run_id: Optional simulation run identifier.

        Returns:
            Latest matching order book snapshot, or `None`.

        Raises:
            KeyError: If `run_id` is supplied and no run exists for it.
        """

        states = (
            [self._get_state(run_id)] if run_id is not None else self._list_states()
        )
        snapshots = sorted(
            (
                snapshot
                for state in states
                for snapshot in state.orderbook_snapshots
                if snapshot.symbol == symbol
            ),
            key=lambda snapshot: (snapshot.as_of, snapshot.source),
        )
        return snapshots[-1] if snapshots else None

    def list_feature_snapshots(self, run_id: UUID) -> list[FeatureSnapshot]:
        """List feature snapshots generated for a simulation run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Feature snapshots generated for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).feature_snapshots)

    def inject_market_event(
        self,
        run_id: UUID,
        type_: Literal[
            "candle_closed",
            "tick",
            "orderbook_snapshot",
            "funding_update",
            "news_event",
            "liquidity_shock",
            "volatility_shock",
            "system_event",
        ],
        symbol: str | None,
        payload: dict[str, object],
        source: str,
        confidence: float,
        simulated_time: datetime | None = None,
    ) -> MarketEvent:
        """Inject a controlled market event into a simulation run.

        Args:
            run_id: Simulation run identifier.
            type_: Market event type.
            symbol: Optional event symbol.
            payload: Event payload.
            source: Event source label.
            confidence: Event confidence score.
            simulated_time: Optional simulated event timestamp.

        Returns:
            Injected market event.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        event = MarketEvent(
            event_id=uuid4(),
            type=type_,
            symbol=symbol,
            simulated_time=simulated_time or state.run.current_sim_time,
            payload=payload,
            source=source,
            confidence=confidence,
        )
        self._event_bus.publish(event)
        state.events.append(event)
        if self._repository is not None:
            self._repository.save_market_event(run_id, event)
        return event

    def build_observation(self, run_id: UUID, symbol: str) -> Observation:
        """Build a point-in-time observation for a run and symbol.

        Args:
            run_id: Simulation run identifier.
            symbol: Symbol to observe.

        Returns:
            Point-in-time observation.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        return self._observation_builder.build(
            run=state.run,
            symbol=symbol,
            as_of=state.run.current_sim_time,
            candles=state.candles,
            events=state.events,
            orderbooks=state.orderbook_snapshots,
            feature_snapshots=state.feature_snapshots,
            positions=state.positions,
            risk_limits=state.risk_limits,
            memory_entries=state.memory_entries,
        )

    def list_observation_snapshots(self, run_id: UUID) -> list[Observation]:
        """List generated observation snapshots for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Observation snapshots for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).observations)

    def get_latest_risk_review(self, run_id: UUID) -> RiskReview | None:
        """Return the latest risk review for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Latest risk review or `None`.
        """

        reviews = self._get_state(run_id).risk_reviews
        return reviews[-1] if reviews else None

    def list_risk_reviews(self, run_id: UUID) -> list[RiskReview]:
        """List risk reviews for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Risk reviews for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).risk_reviews)

    def list_positions(self, run_id: UUID) -> list[Position]:
        """Derive current simulated positions from fills.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Net simulated positions.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        if state.positions or not state.fills:
            return list(state.positions)
        state.positions = self._derive_positions(state)
        return list(state.positions)

    def list_ledger_entries(self, run_id: UUID) -> list[LedgerEntry]:
        """List simulated ledger entries for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Ledger entries for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).ledger_entries)

    def list_portfolio_snapshots(self, run_id: UUID) -> list[PortfolioSnapshot]:
        """List portfolio snapshots for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Portfolio snapshots for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).portfolio_snapshots)

    def list_metric_snapshots(self, run_id: UUID) -> list[MetricSnapshot]:
        """List metric snapshots for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Metric snapshots for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).metric_snapshots)

    def _derive_positions(self, state: SimulationState) -> list[Position]:
        """Derive net simulated positions from state fills.

        Args:
            state: Simulation state containing fills and account state.

        Returns:
            Net simulated positions.
        """

        quantities_by_symbol: dict[str, Decimal] = {}
        notionals_by_symbol: dict[str, Decimal] = {}
        latest_time_by_symbol: dict[str, datetime] = {}
        for fill in state.fills:
            direction = Decimal("-1") if fill.side == "sell" else Decimal("1")
            signed_quantity = direction * fill.quantity
            signed_notional = signed_quantity * fill.price
            quantities_by_symbol[fill.symbol] = (
                quantities_by_symbol.get(fill.symbol, Decimal("0")) + signed_quantity
            )
            notionals_by_symbol[fill.symbol] = (
                notionals_by_symbol.get(fill.symbol, Decimal("0")) + signed_notional
            )
            latest_time_by_symbol[fill.symbol] = fill.filled_at_sim_time

        positions: list[Position] = []
        for symbol, quantity in sorted(quantities_by_symbol.items()):
            if quantity == Decimal("0"):
                continue
            notional = notionals_by_symbol[symbol]
            absolute_quantity = abs(quantity)
            mark_price = abs(notional) / absolute_quantity
            positions.append(
                Position(
                    position_id=uuid5(NAMESPACE_URL, f"{state.run.run_id}:{symbol}"),
                    account_id=state.run.account.account_id,
                    symbol=symbol,
                    side="long" if quantity > Decimal("0") else "short",
                    quantity=absolute_quantity,
                    avg_entry_price=mark_price,
                    mark_price=mark_price,
                    notional=abs(notional),
                    leverage=Decimal("1"),
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=state.run.account.realized_pnl,
                    liquidation_price=None,
                    updated_at_sim_time=latest_time_by_symbol[symbol],
                )
            )
        return positions

    def _build_ledger_entry(
        self,
        run: SimulationRun,
        fill: Fill,
        ledger_update: LedgerUpdate,
    ) -> LedgerEntry:
        """Build a durable ledger entry from one simulated fill.

        Args:
            run: Updated simulation run.
            fill: Simulated fill that changed account state.
            ledger_update: Ledger metadata for the fill.

        Returns:
            Ledger entry domain model.
        """

        return LedgerEntry(
            ledger_entry_id=uuid5(NAMESPACE_URL, f"ledger-entry:{fill.fill_id}"),
            run_id=run.run_id,
            account_id=run.account.account_id,
            fill_id=fill.fill_id,
            entry_type="fill",
            symbol=fill.symbol,
            quantity=fill.quantity,
            price=fill.price,
            notional=ledger_update.notional,
            cash_delta=ledger_update.cash_delta,
            fee=ledger_update.fee,
            realized_pnl_delta=-ledger_update.fee,
            created_at_sim_time=fill.filled_at_sim_time,
            created_at=datetime.now(UTC),
        )

    def _build_portfolio_snapshot(
        self,
        run: SimulationRun,
        positions: tuple[Position, ...],
        source_event_id: UUID,
    ) -> PortfolioSnapshot:
        """Build a portfolio snapshot from current run and position state.

        Args:
            run: Updated simulation run.
            positions: Current derived positions.
            source_event_id: Source event identifier for deterministic snapshot IDs.

        Returns:
            Portfolio snapshot domain model.
        """

        gross_exposure = sum(
            (position.notional for position in positions), Decimal("0")
        )
        net_exposure = sum(
            (
                position.notional if position.side == "long" else -position.notional
                for position in positions
            ),
            Decimal("0"),
        )
        return PortfolioSnapshot(
            snapshot_id=uuid5(NAMESPACE_URL, f"portfolio-snapshot:{source_event_id}"),
            run_id=run.run_id,
            account_id=run.account.account_id,
            simulated_time=run.current_sim_time,
            cash_balance=run.account.cash_balance,
            total_equity=run.account.total_equity,
            realized_pnl=run.account.realized_pnl,
            unrealized_pnl=run.account.unrealized_pnl,
            max_drawdown=run.account.max_drawdown,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            created_at=datetime.now(UTC),
        )

    def _build_metric_snapshot(
        self,
        run: SimulationRun,
        orders: list[SimOrder],
        fills: list[Fill],
        source_event_id: UUID,
    ) -> MetricSnapshot:
        """Build a metric snapshot from current execution artifacts.

        Args:
            run: Updated simulation run.
            orders: Current simulated orders for the run.
            fills: Current simulated fills for the run.
            source_event_id: Source event identifier for deterministic snapshot IDs.

        Returns:
            Metric snapshot domain model.
        """

        metrics = self._metrics_engine.summarize_execution(run, orders, fills)
        return MetricSnapshot(
            snapshot_id=uuid5(NAMESPACE_URL, f"metric-snapshot:{source_event_id}"),
            run_id=run.run_id,
            simulated_time=run.current_sim_time,
            metrics={
                "order_count": metrics.order_count,
                "fill_count": metrics.fill_count,
                "total_fees": str(metrics.total_fees),
                "traded_notional": str(metrics.traded_notional),
                "realized_return": str(metrics.realized_return),
            },
            created_at=datetime.now(UTC),
        )

    def create_decision_review(
        self,
        decision_id: UUID,
        horizon: str,
        realized_return: Decimal,
        max_adverse_excursion: Decimal,
        max_favorable_excursion: Decimal,
        was_correct_directionally: bool,
        error_tags: list[str],
        reviewer_summary: str,
    ) -> DecisionReview:
        """Create a posterior review for an existing decision.

        Args:
            decision_id: Reviewed trade intent identifier.
            horizon: Review horizon label.
            realized_return: Realized return over the horizon.
            max_adverse_excursion: Worst simulated excursion over the horizon.
            max_favorable_excursion: Best simulated excursion over the horizon.
            was_correct_directionally: Whether the direction was correct.
            error_tags: Review error tags.
            reviewer_summary: Human-readable review summary.

        Returns:
            Created decision review.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        state, decision = self._find_decision_state(decision_id)
        review = DecisionReview(
            review_id=uuid4(),
            decision_id=decision.decision_id,
            run_id=decision.run_id,
            horizon=horizon,
            realized_return=realized_return,
            max_adverse_excursion=max_adverse_excursion,
            max_favorable_excursion=max_favorable_excursion,
            was_correct_directionally=was_correct_directionally,
            error_tags=error_tags,
            reviewer_summary=reviewer_summary,
            created_at_sim_time=state.run.current_sim_time,
        )
        state.decision_reviews.append(review)
        if self._repository is not None:
            self._repository.save_decision_review(review)
        return review

    def list_decision_reviews(self, decision_id: UUID) -> list[DecisionReview]:
        """List posterior reviews for an existing decision.

        Args:
            decision_id: Trade intent identifier.

        Returns:
            Decision reviews for the decision.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        state, _decision = self._find_decision_state(decision_id)
        return [
            review
            for review in state.decision_reviews
            if review.decision_id == decision_id
        ]

    def create_memory_entry(
        self,
        run_id: UUID,
        memory_type: MemoryType,
        summary: str,
        content: dict[str, object],
        tags: list[str],
        available_at_sim_time: datetime | None = None,
        decision_id: UUID | None = None,
    ) -> MemoryEntry:
        """Create an auxiliary memory entry for a run.

        Args:
            run_id: Simulation run identifier.
            memory_type: Memory category.
            summary: Short memory summary.
            content: Structured memory payload.
            tags: Search and review tags.
            available_at_sim_time: Optional point-in-time availability.
            decision_id: Optional related decision identifier.

        Returns:
            Created memory entry.

        Raises:
            KeyError: If no run exists for the ID.
            ValueError: If the related decision is outside the run.
        """

        state = self._get_state(run_id)
        if decision_id is not None and not any(
            decision.decision_id == decision_id for decision in state.decisions
        ):
            raise ValueError("Memory decision reference must belong to the run.")
        entry = MemoryEntry(
            memory_id=uuid4(),
            run_id=run_id,
            decision_id=decision_id,
            memory_type=memory_type,
            summary=summary,
            content=content,
            tags=tags,
            available_at_sim_time=available_at_sim_time or state.run.current_sim_time,
            created_at=datetime.now(UTC),
        )
        state.memory_entries.append(entry)
        state.memory_entries.sort(key=lambda memory: memory.available_at_sim_time)
        if self._repository is not None:
            self._repository.save_memory_entry(entry)
        return entry

    def list_memory_entries(self, run_id: UUID) -> list[MemoryEntry]:
        """List auxiliary memory entries for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Memory entries ordered by availability time.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).memory_entries)

    def create_simulation_report(self, run_id: UUID) -> ReportArtifact:
        """Create a structured simulation report from current run state.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Created report artifact.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        run = state.run
        report = ReportArtifact(
            report_id=uuid4(),
            run_id=run_id,
            report_type="simulation",
            title=f"{run.name} simulation report",
            summary=(
                f"{len(state.decisions)} decisions, {len(state.orders)} orders, "
                f"{len(state.fills)} fills, status {run.status}."
            ),
            sections={
                "configuration": run.config,
                "symbols": run.symbols,
                "account": {
                    "cash_balance": str(run.account.cash_balance),
                    "total_equity": str(run.account.total_equity),
                    "realized_pnl": str(run.account.realized_pnl),
                    "unrealized_pnl": str(run.account.unrealized_pnl),
                    "max_drawdown": str(run.account.max_drawdown),
                },
                "activity": {
                    "decision_count": len(state.decisions),
                    "risk_review_count": len(state.risk_reviews),
                    "order_count": len(state.orders),
                    "fill_count": len(state.fills),
                    "memory_count": len(state.memory_entries),
                },
            },
            created_at_sim_time=run.current_sim_time,
            created_at=datetime.now(UTC),
        )
        state.reports.append(report)
        if self._repository is not None:
            self._repository.save_report(report)
        return report

    def create_decision_report(self, decision_id: UUID) -> ReportArtifact:
        """Create a structured decision trace report.

        Args:
            decision_id: Trade intent identifier.

        Returns:
            Created decision report.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        trace = self.build_decision_trace(decision_id)
        state, decision = self._find_decision_state(decision_id)
        report = ReportArtifact(
            report_id=uuid4(),
            run_id=decision.run_id,
            report_type="decision",
            title=f"{decision.symbol} decision report",
            summary=(
                f"{decision.action} intent from {decision.agent_id} with "
                f"{decision.confidence:.2f} confidence."
            ),
            sections={
                "decision": decision.model_dump(mode="json"),
                "agent_run": trace.agent_run.model_dump(mode="json"),
                "agent_messages": [
                    message.model_dump(mode="json") for message in trace.messages
                ],
                "risk_review": (
                    trace.risk_review.model_dump(mode="json")
                    if trace.risk_review is not None
                    else None
                ),
                "order": (
                    trace.order.model_dump(mode="json")
                    if trace.order is not None
                    else None
                ),
                "fill": (
                    trace.fill.model_dump(mode="json")
                    if trace.fill is not None
                    else None
                ),
            },
            created_at_sim_time=state.run.current_sim_time,
            created_at=datetime.now(UTC),
        )
        state.reports.append(report)
        if self._repository is not None:
            self._repository.save_report(report)
        return report

    def list_reports(self, run_id: UUID) -> list[ReportArtifact]:
        """List structured reports for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Reports for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).reports)

    def list_decision_reports(self, decision_id: UUID) -> list[ReportArtifact]:
        """List decision reports for one decision.

        Args:
            decision_id: Trade intent identifier.

        Returns:
            Decision report artifacts.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        state, _decision = self._find_decision_state(decision_id)
        reports: list[ReportArtifact] = []
        for report in state.reports:
            decision_section = report.sections.get("decision")
            if (
                report.report_type == "decision"
                and isinstance(decision_section, dict)
                and decision_section.get("decision_id") == str(decision_id)
            ):
                reports.append(report)
        return reports

    def get_report(self, report_id: UUID) -> ReportArtifact:
        """Get one simulation-backed report by ID.

        Args:
            report_id: Report identifier.

        Returns:
            Report artifact.

        Raises:
            KeyError: If no report exists for the ID.
        """

        if self._repository is not None:
            report = self._repository.get_report(report_id)
            if report is not None:
                return report
        for state in self._list_states():
            for report in state.reports:
                if report.report_id == report_id:
                    return report
        raise KeyError(report_id)

    def create_alert(
        self,
        run_id: UUID,
        category: AlertCategory,
        severity: AlertSeverity,
        message: str,
    ) -> Alert:
        """Create an operator-facing run alert.

        Args:
            run_id: Simulation run identifier.
            category: Alert category.
            severity: Alert severity.
            message: Alert message.

        Returns:
            Created alert.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        alert = Alert(
            alert_id=uuid4(),
            run_id=run_id,
            category=category,
            severity=severity,
            message=message,
            status="open",
            created_at_sim_time=state.run.current_sim_time,
            created_at=datetime.now(UTC),
        )
        state.alerts.append(alert)
        if self._repository is not None:
            self._repository.save_alert(alert)
        return alert

    def list_alerts(self, run_id: UUID) -> list[Alert]:
        """List alerts for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Alerts for the run.

        Raises:
            KeyError: If no run exists for the ID.
        """

        return list(self._get_state(run_id).alerts)

    def update_alert_status(
        self, run_id: UUID, alert_id: UUID, status: AlertStatus
    ) -> Alert:
        """Update a run alert status.

        Args:
            run_id: Simulation run identifier.
            alert_id: Alert identifier.
            status: New alert status.

        Returns:
            Updated alert.

        Raises:
            KeyError: If no run or alert exists for the ID.
        """

        state = self._get_state(run_id)
        for index, alert in enumerate(state.alerts):
            if alert.alert_id == alert_id:
                updated_alert = alert.model_copy(update={"status": status})
                state.alerts[index] = updated_alert
                if self._repository is not None:
                    self._repository.save_alert(updated_alert)
                return updated_alert
        raise KeyError(alert_id)

    def build_benchmark(self, run_id: UUID) -> RunBenchmark:
        """Build deterministic benchmark metrics for a run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Run benchmark summary.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        return build_run_benchmark(
            run=state.run,
            decisions=state.decisions,
            orders=state.orders,
            fills=state.fills,
        )

    def compare_runs(
        self, baseline_run_id: UUID, candidate_run_id: UUID
    ) -> RunComparison:
        """Compare two runs through deterministic benchmark fingerprints.

        Args:
            baseline_run_id: Baseline simulation run identifier.
            candidate_run_id: Candidate simulation run identifier.

        Returns:
            Pairwise run comparison.

        Raises:
            KeyError: If either run does not exist.
        """

        return compare_run_benchmarks(
            baseline=self.build_benchmark(baseline_run_id),
            candidate=self.build_benchmark(candidate_run_id),
        )

    def _find_decision_state(
        self, decision_id: UUID
    ) -> tuple[SimulationState, TradeIntent]:
        """Find the simulation state that owns a decision.

        Args:
            decision_id: Trade intent identifier.

        Returns:
            Owning simulation state and decision.

        Raises:
            KeyError: If no decision exists for the ID.
        """

        if self._repository is not None:
            for decision in self._repository.list_decisions():
                if decision.decision_id == decision_id:
                    return self._get_state(decision.run_id), decision
        for state in self._list_states():
            for decision in state.decisions:
                if decision.decision_id == decision_id:
                    return state, decision
        raise KeyError(decision_id)

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

    def _build_agent_run(self, decision: TradeIntent) -> AgentRun:
        """Build a deterministic agent run for a decision.

        Args:
            decision: Source trade intent.

        Returns:
            Derived agent run.
        """

        return AgentRun(
            agent_run_id=uuid5(NAMESPACE_URL, f"agent-run:{decision.decision_id}"),
            run_id=decision.run_id,
            decision_id=decision.decision_id,
            agent_id=decision.agent_id,
            status="completed",
            started_at_sim_time=decision.created_at_sim_time,
            completed_at_sim_time=decision.created_at_sim_time,
        )

    def _build_agent_messages(
        self, agent_run: AgentRun, decision: TradeIntent
    ) -> list[AgentMessage]:
        """Build deterministic trace messages for a decision.

        Args:
            agent_run: Derived agent run.
            decision: Source trade intent.

        Returns:
            Derived agent messages.
        """

        message_specs: list[tuple[AgentMessageRole, dict[str, object]]] = [
            (
                "system",
                {
                    "boundary": "simulation_only",
                    "live_trading_allowed": False,
                },
            ),
            (
                "observation",
                {
                    "run_id": str(decision.run_id),
                    "symbol": decision.symbol,
                    "created_at_sim_time": decision.created_at_sim_time.isoformat(),
                },
            ),
            (
                "assistant",
                {
                    "action": decision.action,
                    "confidence": decision.confidence,
                    "thesis": decision.thesis,
                    "evidence": decision.evidence,
                },
            ),
        ]
        return [
            AgentMessage(
                message_id=uuid5(
                    NAMESPACE_URL,
                    f"agent-message:{agent_run.agent_run_id}:{index}:{role}",
                ),
                agent_run_id=agent_run.agent_run_id,
                role=role,
                content=content,
                created_at_sim_time=decision.created_at_sim_time,
            )
            for index, (role, content) in enumerate(message_specs)
        ]
