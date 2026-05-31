"""In-memory simulation orchestration service."""

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from tiko.agents import AgentRuntime, RuleBasedTraderAgent
from tiko.analysis import build_run_benchmark, compare_run_benchmarks
from tiko.core.config import Settings
from tiko.data import MarketDataValidator
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
from tiko.domain.decision import DecisionReview, DecisionStatus, TradeIntent
from tiko.domain.market import Candle, FeatureSnapshot, MarketEvent, OrderBookSnapshot
from tiko.domain.memory import MemoryEntry, MemorySearchResult, MemoryType
from tiko.domain.observation import Observation
from tiko.domain.order import Fill, OrderRequest, SimOrder
from tiko.domain.reporting import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertStatus,
    ReportArtifact,
)
from tiko.domain.risk import RiskLimits, RiskReview
from tiko.domain.runtime import BackgroundJob
from tiko.domain.simulation import SimulationRun
from tiko.observation import ObservationBuilder
from tiko.services.portfolio import PortfolioService
from tiko.services.realtime import (
    RealtimeFanoutReceipt,
    RealtimeFanoutService,
    build_alert_envelope,
    build_market_event_envelope,
    build_step_result_envelopes,
)
from tiko.services.risk import RiskService
from tiko.simulation.broker import SimBroker
from tiko.simulation.clock import advance_simulated_time
from tiko.simulation.event_bus import EventBus
from tiko.simulation.ledger import (
    FundingUpdate,
    LedgerUpdate,
    apply_fill_to_ledger,
    apply_funding_to_ledger,
    calculate_fill_accounting,
)
from tiko.simulation.metrics import MetricsEngine
from tiko.simulation.replay import MarketReplay, MarketReplayExhausted
from tiko.simulation.slippage import SlippageContext
from tiko.simulation.state import SimulationState, SimulationStepResult
from tiko.simulation.synthetic import generate_synthetic_candle

MEMORY_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
SIMULATION_STEP_SECONDS = Decimal("3600")


class SimulationService:
    """Coordinate deterministic simulation runs with optional persistence."""

    def __init__(
        self,
        settings: Settings,
        repository: SimulationRepository | None = None,
        realtime_fanout: RealtimeFanoutService | None = None,
    ) -> None:
        """Initialize service dependencies and state.

        Args:
            settings: Application settings.
            repository: Optional persistence repository.
            realtime_fanout: Optional realtime fanout publisher.
        """

        self._settings = settings
        self._repository = repository
        self._realtime_fanout = realtime_fanout
        self._realtime_fanout_receipts: list[RealtimeFanoutReceipt] = []
        self._states: dict[UUID, SimulationState] = {}
        self._portfolio_service = PortfolioService(
            taker_fee_bps=settings.sim_broker_taker_fee_bps,
            estimated_slippage_bps=settings.sim_broker_slippage_bps,
        )
        self._broker = SimBroker(
            fee_bps=settings.sim_broker_taker_fee_bps,
            slippage_bps=settings.sim_broker_slippage_bps,
            maker_fee_bps=settings.sim_broker_maker_fee_bps,
            slippage_volatility_multiplier=(
                settings.sim_broker_slippage_volatility_multiplier
            ),
            slippage_liquidity_multiplier=(
                settings.sim_broker_slippage_liquidity_multiplier
            ),
            max_market_spread_bps=settings.sim_broker_max_market_spread_bps,
            min_market_depth_1pct_usd=settings.sim_broker_min_market_depth_1pct_usd,
            allow_market=settings.sim_broker_allow_market,
            allow_limit=settings.sim_broker_allow_limit,
        )
        self._event_bus = EventBus()
        self._observation_builder = ObservationBuilder()
        self._metrics_engine = MetricsEngine()

    def create_run(
        self,
        name: str,
        symbols: list[str],
        start_sim_time: datetime | None = None,
        replay_candles: Sequence[Candle] | None = None,
        *,
        mode: Literal["live_simulated_clock", "synthetic_market"] = "synthetic_market",
        end_sim_time: datetime | None = None,
        speed_multiplier: Decimal = Decimal("1"),
        timeframe: str = "1h",
        decision_interval: str = "1h",
        initial_equity: Decimal | None = None,
    ) -> SimulationRun:
        """Create a new process-local simulation run.

        Args:
            name: Human-readable run name.
            symbols: Symbols included in the simulation.
            start_sim_time: Optional start time. Defaults to current UTC hour.
            replay_candles: Optional normalized candles for historical replay.
            mode: Non-replay simulation runtime mode.
            end_sim_time: Optional configured end time.
            speed_multiplier: Simulated clock speed multiplier.
            timeframe: Primary market data timeframe label.
            decision_interval: Decision cadence label.
            initial_equity: Optional initial simulated account equity.

        Returns:
            Created simulation run.

        Raises:
            ValueError: If configuration values are invalid.
        """

        if speed_multiplier <= Decimal("0"):
            raise ValueError("speed_multiplier must be greater than zero.")
        if not timeframe:
            raise ValueError("timeframe must be non-empty.")
        if not decision_interval:
            raise ValueError("decision_interval must be non-empty.")
        initial_equity_value = (
            initial_equity
            if initial_equity is not None
            else Decimal(self._settings.default_initial_equity)
        )
        if initial_equity_value <= Decimal("0"):
            raise ValueError("initial_equity must be greater than zero.")
        run_id = uuid4()
        market_replay = (
            MarketReplay(replay_candles, symbols)
            if replay_candles is not None
            else None
        )
        account = SimAccount(
            account_id=uuid4(),
            name=f"{name}-account",
            initial_equity=initial_equity_value,
            cash_balance=initial_equity_value,
            total_equity=initial_equity_value,
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
        if end_sim_time is not None and end_sim_time <= start_time:
            raise ValueError("end_sim_time must be after start_sim_time.")
        if replay_candles is not None and end_sim_time is not None:
            self._validate_replay_candles_for_run(replay_candles, symbols, end_sim_time)
        resolved_mode: Literal[
            "historical_replay", "live_simulated_clock", "synthetic_market"
        ] = "historical_replay" if market_replay is not None else mode
        run = SimulationRun(
            run_id=run_id,
            name=name,
            status="created",
            mode=resolved_mode,
            account=account,
            symbols=symbols,
            start_sim_time=start_time,
            current_sim_time=start_time,
            end_sim_time=end_sim_time,
            speed_multiplier=speed_multiplier,
            config={
                "data_source": "replay" if market_replay is not None else "synthetic",
                "timeframe": timeframe,
                "decision_interval": decision_interval,
                "initial_equity": str(initial_equity_value),
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

    def _validate_replay_candles_for_run(
        self,
        replay_candles: Sequence[Candle],
        symbols: Sequence[str],
        run_end: datetime,
    ) -> None:
        """Validate selected replay candles against the run time boundary.

        Args:
            replay_candles: Candidate replay candles.
            symbols: Symbols included in the simulation run.
            run_end: Configured run end time.

        Raises:
            ValueError: If selected replay candles fail data validation.
        """

        symbol_set = set(symbols)
        selected_candles = tuple(
            candle
            for candle in replay_candles
            if not symbol_set or candle.symbol in symbol_set
        )
        report = MarketDataValidator().validate_candles(
            selected_candles, run_end=run_end
        )
        if not report.has_errors():
            return
        first_error = next(
            issue for issue in report.issues if issue.severity == "error"
        )
        raise ValueError(
            "Replay candles fail data quality validation: "
            f"{first_error.code} at {first_error.open_time}."
        )

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
        max_leverage: Decimal | None = None,
        max_drawdown: Decimal | None = None,
        max_daily_loss: Decimal | None = None,
    ) -> RiskLimits:
        """Update active risk limits for future simulation steps.

        Args:
            run_id: Simulation run identifier.
            minimum_confidence: Minimum confidence required for approval.
            minimum_data_quality_score: Minimum observation quality required.
            max_target_weight: Maximum absolute target portfolio weight.
            max_order_notional: Maximum simulated order notional.
            max_leverage: Optional maximum allowed leverage.
            max_drawdown: Optional maximum drawdown ratio.
            max_daily_loss: Optional maximum daily loss ratio.

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
            max_leverage=(
                max_leverage
                if max_leverage is not None
                else state.risk_limits.max_leverage
            ),
            max_drawdown=(
                max_drawdown
                if max_drawdown is not None
                else state.risk_limits.max_drawdown
            ),
            max_daily_loss=(
                max_daily_loss
                if max_daily_loss is not None
                else state.risk_limits.max_daily_loss
            ),
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
            max_leverage=self._settings.max_leverage,
            max_drawdown=self._settings.max_drawdown,
            max_daily_loss=self._settings.max_daily_loss,
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
            max_leverage=limits.max_leverage,
            max_drawdown=limits.max_drawdown,
            max_daily_loss=limits.max_daily_loss,
            allow_short=self._settings.sim_broker_allow_short,
            allow_leverage=self._settings.sim_broker_allow_leverage,
        )

    def _apply_step_decision_status(
        self,
        decision: TradeIntent,
        risk_review: RiskReview,
        order_request: OrderRequest | None,
    ) -> TradeIntent:
        """Attach the current decision lifecycle status for a completed step.

        Args:
            decision: Source trade intent.
            risk_review: Risk review produced for the decision.
            order_request: Portfolio order request produced from the review.

        Returns:
            Trade intent with current lifecycle status.
        """

        if risk_review.status in {"rejected", "circuit_blocked"}:
            status: DecisionStatus = risk_review.status
        elif order_request is None:
            status = "no_order"
        else:
            status = "converted_to_order"
        return decision.model_copy(update={"status": status})

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
            realtime_events=self._repository.list_realtime_events(run_id),
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
        if status != "running":
            state.runtime_wall_time = None
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

    def advance_running_runs(
        self,
        now: datetime | None = None,
        confidence: float = 0.7,
    ) -> list[SimulationStepResult]:
        """Advance running simulations when wall-clock time makes steps due.

        Args:
            now: Optional wall-clock evaluation time. Defaults to current UTC time.
            confidence: Synthetic agent confidence used for due simulation steps.

        Returns:
            Step results generated by the scheduler tick.
        """

        tick_time = now or datetime.now(UTC)
        results: list[SimulationStepResult] = []
        for state in self._list_states():
            if state.run.status != "running":
                state.runtime_wall_time = None
                continue
            if state.runtime_wall_time is None:
                state.runtime_wall_time = tick_time
                continue
            elapsed_seconds = Decimal(
                str(max((tick_time - state.runtime_wall_time).total_seconds(), 0.0))
            )
            due_steps = int(
                (elapsed_seconds * state.run.speed_multiplier)
                // SIMULATION_STEP_SECONDS
            )
            if due_steps <= 0:
                continue
            wall_seconds_used = (
                Decimal(due_steps) * SIMULATION_STEP_SECONDS
            ) / state.run.speed_multiplier
            state.runtime_wall_time = state.runtime_wall_time + timedelta(
                seconds=float(wall_seconds_used)
            )
            for _step_index in range(due_steps):
                try:
                    results.append(self.step_run(state.run.run_id, confidence))
                except MarketReplayExhausted:
                    state.runtime_wall_time = None
                    break
        return results

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
        self._ensure_run_can_step(state.run)
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
        run_status = (
            "completed"
            if state.run.end_sim_time is not None
            and next_time >= state.run.end_sim_time
            else "running"
        )
        decision_run = state.run.model_copy(
            update={
                "status": run_status,
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
            observation_id=observation.observation_id,
            confidence=confidence,
            data_quality_score=observation.data_quality.score,
            events=observation.events,
            input_data_as_of=observation.as_of,
            simulated_time=next_time,
        )
        risk_review = self._build_risk_service(state.risk_limits).review(
            intent, account=decision_run.account
        )
        order = None
        fill = None
        portfolio_order_plan = self._portfolio_service.create_order_plan(
            account=decision_run.account,
            intent=intent,
            risk_review=risk_review,
            reference_price=candle.close,
            positions=state.positions,
        )
        order_request = portfolio_order_plan.order_request
        intent = self._apply_step_decision_status(intent, risk_review, order_request)
        account = decision_run.account
        ledger_update: LedgerUpdate | None = None
        if order_request is not None:
            slippage_context = self._build_slippage_context(
                order_request,
                candle.close,
                orderbook_snapshot,
                feature_snapshot,
            )
            order, fill = self._broker.submit_market_order(
                order_request,
                candle.close,
                slippage_context=slippage_context,
            )
            state.orders.append(order)
            if fill is not None:
                ledger_update = apply_fill_to_ledger(
                    account,
                    fill,
                    prior_fills=state.fills,
                )
                account = ledger_update.account
                state.fills.append(fill)
        ledger_run = decision_run.model_copy(update={"account": account})
        state.run = ledger_run
        agent_run = self._build_agent_run(intent)
        agent_messages = tuple(self._build_agent_messages(agent_run, intent))
        state.observations.append(observation)
        state.agent_runs.append(agent_run)
        state.agent_messages.extend(agent_messages)
        state.decisions.append(intent)
        state.risk_reviews.append(risk_review)
        positions = tuple(
            self._derive_positions(
                state,
                mark_prices={symbol: candle.close},
                as_of=next_time,
            )
        )
        state.positions = list(positions)
        funded_account = ledger_run.account
        funding_update: FundingUpdate | None = None
        if self._should_apply_funding(state.step_index + 1, positions):
            funding_update = apply_funding_to_ledger(
                funded_account,
                positions,
                self._settings.synthetic_funding_rate,
            )
            funded_account = funding_update.account
        marked_account = self._mark_account_to_market(funded_account, positions)
        updated_run = ledger_run.model_copy(update={"account": marked_account})
        state.run = updated_run
        state.step_index += 1
        ledger_entry = (
            self._build_ledger_entry(updated_run, fill, ledger_update)
            if fill is not None and ledger_update is not None
            else None
        )
        if ledger_entry is not None:
            state.ledger_entries.append(ledger_entry)
        funding_ledger_entry = (
            self._build_funding_ledger_entry(updated_run, positions, funding_update)
            if funding_update is not None
            else None
        )
        if funding_ledger_entry is not None:
            state.ledger_entries.append(funding_ledger_entry)
        portfolio_snapshot = self._build_portfolio_snapshot(
            updated_run, positions, event.event_id
        )
        metric_snapshot = self._build_metric_snapshot(
            updated_run,
            state.orders,
            state.fills,
            state.ledger_entries,
            event.event_id,
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
            portfolio_order_plan=portfolio_order_plan,
            order=order,
            fill=fill,
            positions=positions,
            ledger_entry=ledger_entry,
            funding_ledger_entry=funding_ledger_entry,
            portfolio_snapshot=portfolio_snapshot,
            metric_snapshot=metric_snapshot,
        )
        realtime_envelopes = build_step_result_envelopes(result)
        state.realtime_events.extend(realtime_envelopes)
        if self._repository is not None:
            self._repository.save_step_result(
                result,
                realtime_envelopes=realtime_envelopes,
            )
        self._publish_realtime_envelopes(realtime_envelopes)
        return result

    def _ensure_run_can_step(self, run: SimulationRun) -> None:
        """Validate that a simulation run can produce another manual step.

        Args:
            run: Simulation run about to be stepped.

        Raises:
            ValueError: If the run is in a terminal lifecycle state.
        """

        if run.status in {"stopped", "completed"}:
            raise ValueError(f"Simulation run is {run.status} and cannot be stepped.")

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
            state.run.symbols[0],
            state.step_index,
            next_time,
            seed=self._settings.synthetic_seed,
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

    def _build_slippage_context(
        self,
        order_request: OrderRequest,
        reference_price: Decimal,
        orderbook_snapshot: OrderBookSnapshot,
        feature_snapshot: FeatureSnapshot,
    ) -> SlippageContext:
        """Build point-in-time slippage context for one market order.

        Args:
            order_request: Order request to execute.
            reference_price: Market reference price used for execution.
            orderbook_snapshot: Current point-in-time order book snapshot.
            feature_snapshot: Current point-in-time feature snapshot.

        Returns:
            Slippage context for simulated market execution.
        """

        return SlippageContext(
            volatility_bps=self._extract_feature_volatility_bps(feature_snapshot),
            spread_bps=orderbook_snapshot.spread_bps,
            order_notional=order_request.quantity * reference_price,
            depth_1pct_usd=orderbook_snapshot.depth_1pct_usd,
        )

    def _extract_feature_volatility_bps(
        self, feature_snapshot: FeatureSnapshot
    ) -> Decimal:
        """Extract a volatility proxy from point-in-time feature data.

        Args:
            feature_snapshot: Current feature snapshot.

        Returns:
            Absolute one-step return expressed in basis points.
        """

        value = feature_snapshot.features.get("one_step_return")
        if value is None:
            return Decimal("0")
        try:
            one_step_return = Decimal(str(value))
        except InvalidOperation:
            return Decimal("0")
        if not one_step_return.is_finite():
            return Decimal("0")
        return abs(one_step_return) * Decimal("10000")

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

    def apply_agent_inference_job(self, job: BackgroundJob) -> DecisionTrace:
        """Apply a completed agent inference job to simulation trace state.

        Args:
            job: Completed agent inference runtime job.

        Returns:
            Reconciled decision trace.

        Raises:
            ValueError: If the job or trace payload is invalid.
            KeyError: If the simulation run does not exist.
        """

        if job.job_type != "agent_inference":
            raise ValueError("Only agent_inference jobs can update agent traces.")
        if job.status != "completed":
            raise ValueError("Only completed agent_inference jobs can be applied.")
        observation = Observation.model_validate(
            self._require_mapping(job.payload, "observation")
        )
        decision = TradeIntent.model_validate(
            self._require_mapping(job.result, "intent")
        )
        agent_run = AgentRun.model_validate(
            self._require_mapping(job.result, "agent_run")
        )
        messages = tuple(
            AgentMessage.model_validate(item)
            for item in self._require_mapping_sequence(job.result, "agent_messages")
        )
        self._validate_agent_trace_payload(observation, decision, agent_run, messages)
        decision = self._enrich_agent_trace_decision(
            observation=observation,
            decision=decision,
            agent_run=agent_run,
        )
        state = self._get_state(decision.run_id)
        if not any(
            candidate.observation_id == observation.observation_id
            for candidate in state.observations
        ):
            state.observations.append(observation)
        if not any(
            candidate.decision_id == decision.decision_id
            for candidate in state.decisions
        ):
            state.decisions.append(decision)
        if not any(
            candidate.agent_run_id == agent_run.agent_run_id
            for candidate in state.agent_runs
        ):
            state.agent_runs.append(agent_run)
        existing_message_ids = {
            candidate.message_id for candidate in state.agent_messages
        }
        state.agent_messages.extend(
            message
            for message in messages
            if message.message_id not in existing_message_ids
        )
        if self._repository is not None:
            self._repository.save_agent_trace(
                observation=observation,
                decision=decision,
                agent_run=agent_run,
                agent_messages=messages,
            )
        return DecisionTrace(
            decision=decision,
            agent_run=agent_run,
            messages=list(messages),
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

    def list_realtime_fanout_receipts(self) -> list[RealtimeFanoutReceipt]:
        """List realtime fanout receipts recorded by this service.

        Returns:
            Realtime fanout receipts in publish order.
        """

        return list(self._realtime_fanout_receipts)

    def list_realtime_events(self, run_id: UUID) -> list[dict[str, object]]:
        """List canonical realtime event envelopes for a simulation run.

        Args:
            run_id: Simulation run identifier.

        Returns:
            Realtime event envelopes ordered for replay.

        Raises:
            KeyError: If no run exists for the ID.
        """

        state = self._get_state(run_id)
        if self._repository is not None:
            return self._repository.list_realtime_events(run_id)
        return sorted(
            state.realtime_events,
            key=lambda event: (
                str(event["simulated_time"]),
                str(event["topic"]),
                str(event["event_id"]),
            ),
        )

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
        realtime_envelope = build_market_event_envelope(run_id, event)
        state.realtime_events.append(realtime_envelope)
        if self._repository is not None:
            self._repository.save_market_event(run_id, event)
            self._repository.save_realtime_events([realtime_envelope])
        self._publish_realtime_envelopes([realtime_envelope])
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

    def _derive_positions(
        self,
        state: SimulationState,
        mark_prices: dict[str, Decimal] | None = None,
        as_of: datetime | None = None,
    ) -> list[Position]:
        """Derive net simulated positions from state fills.

        Args:
            state: Simulation state containing fills and account state.
            mark_prices: Optional current mark prices by symbol.
            as_of: Optional simulated time for marked positions.

        Returns:
            Net simulated positions.
        """

        accounting = calculate_fill_accounting(state.fills)
        positions: list[Position] = []
        for accounted_position in accounting.positions:
            mark_price = (
                mark_prices.get(
                    accounted_position.symbol,
                    accounted_position.avg_entry_price,
                )
                if mark_prices is not None
                else accounted_position.avg_entry_price
            )
            unrealized_pnl = self._calculate_unrealized_pnl(
                side=accounted_position.side,
                quantity=accounted_position.quantity,
                avg_entry_price=accounted_position.avg_entry_price,
                mark_price=mark_price,
            )
            leverage = Decimal("1")
            positions.append(
                Position(
                    position_id=uuid5(
                        NAMESPACE_URL,
                        f"{state.run.run_id}:{accounted_position.symbol}",
                    ),
                    account_id=state.run.account.account_id,
                    symbol=accounted_position.symbol,
                    side=accounted_position.side,
                    quantity=accounted_position.quantity,
                    avg_entry_price=accounted_position.avg_entry_price,
                    mark_price=mark_price,
                    notional=accounted_position.quantity * mark_price,
                    leverage=leverage,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=accounted_position.realized_pnl,
                    liquidation_price=self._calculate_liquidation_price(
                        accounted_position.side,
                        accounted_position.avg_entry_price,
                        leverage,
                    ),
                    updated_at_sim_time=as_of or accounted_position.latest_time,
                )
            )
        return positions

    def _calculate_unrealized_pnl(
        self,
        side: Literal["long", "short"],
        quantity: Decimal,
        avg_entry_price: Decimal,
        mark_price: Decimal,
    ) -> Decimal:
        """Calculate unrealized PnL for one marked position.

        Args:
            side: Position side.
            quantity: Absolute position quantity.
            avg_entry_price: Average entry price.
            mark_price: Current mark price.

        Returns:
            Unrealized PnL.
        """

        if side == "long":
            return (mark_price - avg_entry_price) * quantity
        return (avg_entry_price - mark_price) * quantity

    def _calculate_liquidation_price(
        self,
        side: Literal["long", "short"],
        avg_entry_price: Decimal,
        leverage: Decimal,
    ) -> Decimal | None:
        """Calculate a deterministic approximate liquidation price.

        Args:
            side: Position side.
            avg_entry_price: Average entry price.
            leverage: Simulated position leverage.

        Returns:
            Approximate liquidation price or `None` when leverage is invalid.
        """

        if leverage <= Decimal("0"):
            return None
        leverage_buffer = Decimal("1") / leverage
        if side == "long":
            return max(
                Decimal("0"),
                avg_entry_price * (Decimal("1") - leverage_buffer),
            )
        return avg_entry_price * (Decimal("1") + leverage_buffer)

    def _mark_account_to_market(
        self,
        account: SimAccount,
        positions: Sequence[Position],
    ) -> SimAccount:
        """Mark account equity and drawdown from current positions.

        Args:
            account: Account after cash and fee updates.
            positions: Current marked positions.

        Returns:
            Account with updated equity, unrealized PnL, and drawdown.
        """

        signed_position_value = sum(
            (
                position.notional if position.side == "long" else -position.notional
                for position in positions
            ),
            Decimal("0"),
        )
        unrealized_pnl = sum(
            (position.unrealized_pnl for position in positions), Decimal("0")
        )
        raw_total_equity = account.cash_balance + signed_position_value
        total_equity = max(Decimal("0"), raw_total_equity)
        account_status = (
            "liquidated" if raw_total_equity <= Decimal("0") else account.status
        )
        drawdown = (
            (total_equity - account.initial_equity) / account.initial_equity
            if total_equity < account.initial_equity
            else Decimal("0")
        )
        return account.model_copy(
            update={
                "total_equity": total_equity,
                "unrealized_pnl": unrealized_pnl,
                "max_drawdown": min(account.max_drawdown, drawdown),
                "status": account_status,
            }
        )

    def _should_apply_funding(
        self,
        completed_step_number: int,
        positions: Sequence[Position],
    ) -> bool:
        """Determine whether simulated funding should be applied.

        Args:
            completed_step_number: One-based completed step number.
            positions: Current marked positions.

        Returns:
            Whether funding should be applied for this step.
        """

        return (
            self._settings.synthetic_funding_rate != Decimal("0")
            and len(positions) > 0
            and completed_step_number % self._settings.synthetic_funding_interval_steps
            == 0
        )

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
            realized_pnl_delta=ledger_update.realized_pnl_delta,
            created_at_sim_time=fill.filled_at_sim_time,
            created_at=datetime.now(UTC),
        )

    def _build_funding_ledger_entry(
        self,
        run: SimulationRun,
        positions: Sequence[Position],
        funding_update: FundingUpdate,
    ) -> LedgerEntry:
        """Build a durable ledger entry for simulated funding.

        Args:
            run: Updated simulation run.
            positions: Current marked positions.
            funding_update: Funding metadata for the interval.

        Returns:
            Funding ledger entry domain model.
        """

        symbols = ",".join(sorted({position.symbol for position in positions}))
        return LedgerEntry(
            ledger_entry_id=uuid5(
                NAMESPACE_URL,
                f"funding-ledger-entry:{run.run_id}:{run.current_sim_time.isoformat()}",
            ),
            run_id=run.run_id,
            account_id=run.account.account_id,
            fill_id=None,
            entry_type="funding",
            symbol=symbols or None,
            quantity=sum((position.quantity for position in positions), Decimal("0")),
            price=None,
            notional=funding_update.notional,
            cash_delta=funding_update.cash_delta,
            fee=Decimal("0"),
            realized_pnl_delta=funding_update.cash_delta,
            created_at_sim_time=run.current_sim_time,
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
        ledger_entries: Sequence[LedgerEntry],
        source_event_id: UUID,
    ) -> MetricSnapshot:
        """Build a metric snapshot from current execution artifacts.

        Args:
            run: Updated simulation run.
            orders: Current simulated orders for the run.
            fills: Current simulated fills for the run.
            ledger_entries: Current simulated ledger entries for the run.
            source_event_id: Source event identifier for deterministic snapshot IDs.

        Returns:
            Metric snapshot domain model.
        """

        metrics = self._metrics_engine.summarize_execution(run, orders, fills)
        cumulative_funding = sum(
            (
                entry.cash_delta
                for entry in ledger_entries
                if entry.entry_type == "funding"
            ),
            Decimal("0"),
        )
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
                "cumulative_funding": str(cumulative_funding),
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
        reviewed_decision = decision.model_copy(update={"status": "reviewed"})
        self._replace_state_decision(state, reviewed_decision)
        if self._repository is not None:
            self._repository.save_decision(reviewed_decision)
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

    def search_memory_entries(
        self,
        run_id: UUID,
        query: str,
        as_of: datetime | None = None,
        limit: int = 5,
    ) -> list[MemorySearchResult]:
        """Search available memory entries for one run.

        Args:
            run_id: Simulation run identifier.
            query: Retrieval query text.
            as_of: Optional simulated-time cutoff. The run time is used when omitted.
            limit: Maximum number of results.

        Returns:
            Ranked memory search results.

        Raises:
            KeyError: If no run exists for the ID.
            ValueError: If the query or limit is invalid.
        """

        if limit <= 0:
            raise ValueError("Memory search limit must be positive.")
        query_terms = self._tokenize_memory_text(query)
        if not query_terms:
            raise ValueError("Memory search query must include at least one token.")
        state = self._get_state(run_id)
        cutoff = as_of if as_of is not None else state.run.current_sim_time
        results: list[MemorySearchResult] = []
        for entry in state.memory_entries:
            if entry.available_at_sim_time > cutoff:
                continue
            result = self._score_memory_entry(entry, query_terms)
            if result is not None:
                results.append(result)
        results.sort(
            key=lambda result: (
                -result.score,
                -result.entry.available_at_sim_time.timestamp(),
                -result.entry.created_at.timestamp(),
                str(result.entry.memory_id),
            )
        )
        return results[:limit]

    def _score_memory_entry(
        self,
        entry: MemoryEntry,
        query_terms: Sequence[str],
    ) -> MemorySearchResult | None:
        """Score one memory entry against query terms.

        Args:
            entry: Candidate memory entry.
            query_terms: Unique normalized query terms.

        Returns:
            Search result when any term matches, otherwise `None`.
        """

        document = self._build_memory_search_document(entry)
        document_tokens = set(self._tokenize_memory_text(document))
        normalized_document = document.lower()
        matched_terms = [
            term
            for term in query_terms
            if term in document_tokens or term in normalized_document
        ]
        if not matched_terms:
            return None
        return MemorySearchResult(
            entry=entry,
            score=len(matched_terms) / len(query_terms),
            matched_terms=matched_terms,
        )

    def _build_memory_search_document(self, entry: MemoryEntry) -> str:
        """Build normalized searchable text for one memory entry.

        Args:
            entry: Memory entry.

        Returns:
            Searchable text document.
        """

        content_text = json.dumps(
            entry.content,
            default=str,
            sort_keys=True,
        )
        return " ".join(
            [
                entry.memory_type,
                entry.summary,
                " ".join(entry.tags),
                content_text,
            ]
        )

    def _tokenize_memory_text(self, value: str) -> list[str]:
        """Tokenize memory retrieval text.

        Args:
            value: Raw text.

        Returns:
            Unique normalized tokens preserving first-seen order.
        """

        normalized_value = value.strip().lower()
        if not normalized_value:
            return []
        tokens = MEMORY_TOKEN_PATTERN.findall(normalized_value)
        if not tokens:
            tokens = [normalized_value]
        unique_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for token in tokens:
            if token in seen_tokens:
                continue
            unique_tokens.append(token)
            seen_tokens.add(token)
        return unique_tokens

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
                "dataset": self._build_report_dataset_section(state),
                "timeline": self._build_report_timeline_section(state),
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
                "equity_curve": self._build_report_equity_curve(state),
                "drawdown_curve": self._build_report_drawdown_curve(state),
                "position_curve": self._build_report_position_curve(state),
                "trades": self._build_report_trade_list(state),
                "key_metrics": self._build_report_key_metrics(state),
                "risk_events": self._build_report_risk_events(state),
                "agent_performance": self._build_report_agent_performance(state),
                "error_attribution": self._build_report_error_attribution(state),
            },
            created_at_sim_time=run.current_sim_time,
            created_at=datetime.now(UTC),
        )
        state.reports.append(report)
        if self._repository is not None:
            self._repository.save_report(report)
        return report

    def _build_report_dataset_section(
        self, state: SimulationState
    ) -> dict[str, object]:
        """Build dataset context for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Dataset report section.
        """

        replay = state.market_replay
        return {
            "data_source": state.run.config.get("data_source", "unknown"),
            "mode": state.run.mode,
            "symbols": state.run.symbols,
            "emitted_candle_count": len(state.candles),
            "remaining_replay_candles": replay.remaining() if replay is not None else 0,
        }

    def _build_report_timeline_section(
        self, state: SimulationState
    ) -> dict[str, object]:
        """Build timeline context for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Timeline report section.
        """

        return {
            "start_sim_time": state.run.start_sim_time.isoformat(),
            "current_sim_time": state.run.current_sim_time.isoformat(),
            "created_at": state.run.created_at.isoformat(),
            "status": state.run.status,
            "speed_multiplier": str(state.run.speed_multiplier),
        }

    def _build_report_equity_curve(
        self, state: SimulationState
    ) -> list[dict[str, object]]:
        """Build an equity curve from portfolio snapshots.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Equity curve points.
        """

        return [
            {
                "simulated_time": snapshot.simulated_time.isoformat(),
                "cash_balance": str(snapshot.cash_balance),
                "total_equity": str(snapshot.total_equity),
                "realized_pnl": str(snapshot.realized_pnl),
                "unrealized_pnl": str(snapshot.unrealized_pnl),
            }
            for snapshot in state.portfolio_snapshots
        ]

    def _build_report_drawdown_curve(
        self, state: SimulationState
    ) -> list[dict[str, object]]:
        """Build a drawdown curve from portfolio snapshots.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Drawdown curve points.
        """

        return [
            {
                "simulated_time": snapshot.simulated_time.isoformat(),
                "max_drawdown": str(snapshot.max_drawdown),
                "gross_exposure": str(snapshot.gross_exposure),
                "net_exposure": str(snapshot.net_exposure),
            }
            for snapshot in state.portfolio_snapshots
        ]

    def _build_report_position_curve(
        self, state: SimulationState
    ) -> list[dict[str, object]]:
        """Build current position exposure points for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Position exposure points.
        """

        return [
            {
                "symbol": position.symbol,
                "side": position.side,
                "quantity": str(position.quantity),
                "notional": str(position.notional),
                "mark_price": str(position.mark_price),
                "updated_at_sim_time": position.updated_at_sim_time.isoformat(),
            }
            for position in state.positions
        ]

    def _build_report_trade_list(
        self, state: SimulationState
    ) -> list[dict[str, object]]:
        """Build simulated trade rows for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Simulated trade rows.
        """

        orders_by_id = {order.order_id: order for order in state.orders}
        rows: list[dict[str, object]] = []
        for fill in state.fills:
            order = orders_by_id.get(fill.order_id)
            rows.append(
                {
                    "fill_id": str(fill.fill_id),
                    "order_id": str(fill.order_id),
                    "decision_id": str(order.decision_id)
                    if order is not None and order.decision_id is not None
                    else None,
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "quantity": str(fill.quantity),
                    "price": str(fill.price),
                    "fee": str(fill.fee),
                    "slippage_bps": str(fill.slippage_bps),
                    "filled_at_sim_time": fill.filled_at_sim_time.isoformat(),
                }
            )
        return rows

    def _build_report_key_metrics(self, state: SimulationState) -> dict[str, object]:
        """Build key performance metrics for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Key metrics report section.
        """

        latest_metrics = (
            state.metric_snapshots[-1].metrics if state.metric_snapshots else {}
        )
        return {
            "latest": latest_metrics,
            "history": [
                {
                    "simulated_time": snapshot.simulated_time.isoformat(),
                    "metrics": snapshot.metrics,
                }
                for snapshot in state.metric_snapshots
            ],
        }

    def _build_report_risk_events(
        self, state: SimulationState
    ) -> list[dict[str, object]]:
        """Build risk event rows for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Risk event rows.
        """

        return [
            {
                "review_id": str(review.review_id),
                "decision_id": str(review.decision_id),
                "status": review.status,
                "reasons": review.reasons,
                "triggered_rules": review.triggered_rules,
                "created_at_sim_time": review.created_at_sim_time.isoformat(),
            }
            for review in state.risk_reviews
            if review.status != "approved" or review.reasons or review.triggered_rules
        ]

    def _build_report_agent_performance(
        self, state: SimulationState
    ) -> dict[str, object]:
        """Build agent performance context for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Agent performance report section.
        """

        actions: dict[str, int] = {}
        statuses: dict[str, int] = {}
        confidence_sum = 0.0
        for decision in state.decisions:
            actions[decision.action] = actions.get(decision.action, 0) + 1
            confidence_sum += decision.confidence
        for agent_run in state.agent_runs:
            statuses[agent_run.status] = statuses.get(agent_run.status, 0) + 1
        decision_count = len(state.decisions)
        average_confidence = confidence_sum / decision_count if decision_count else 0.0
        return {
            "decision_count": decision_count,
            "agent_run_count": len(state.agent_runs),
            "message_count": len(state.agent_messages),
            "actions": actions,
            "agent_run_statuses": statuses,
            "average_confidence": average_confidence,
        }

    def _build_report_error_attribution(
        self, state: SimulationState
    ) -> dict[str, object]:
        """Build error attribution context for a simulation report.

        Args:
            state: Simulation state used for report generation.

        Returns:
            Error attribution report section.
        """

        risk_events = self._build_report_risk_events(state)
        failed_agent_runs = [
            {
                "agent_run_id": str(agent_run.agent_run_id),
                "agent_id": agent_run.agent_id,
                "status": agent_run.status,
            }
            for agent_run in state.agent_runs
            if agent_run.status == "failed"
        ]
        return {
            "risk_event_count": len(risk_events),
            "alert_count": len(state.alerts),
            "failed_agent_run_count": len(failed_agent_runs),
            "alerts": [
                {
                    "alert_id": str(alert.alert_id),
                    "category": alert.category,
                    "severity": alert.severity,
                    "status": alert.status,
                    "message": alert.message,
                }
                for alert in state.alerts
            ],
            "failed_agent_runs": failed_agent_runs,
        }

    def _find_decision_observation(
        self, state: SimulationState, decision: TradeIntent
    ) -> Observation | None:
        """Find the observation snapshot that produced a decision.

        Args:
            state: Simulation state used for report generation.
            decision: Trade intent being reported.

        Returns:
            Matching observation snapshot when one can be inferred.
        """

        return next(
            (
                observation
                for observation in state.observations
                if observation.run_id == decision.run_id
                and observation.symbol == decision.symbol
                and observation.as_of == decision.created_at_sim_time
            ),
            None,
        )

    def _build_decision_report_agent_subreports(
        self, trace: DecisionTrace
    ) -> list[dict[str, object]]:
        """Build per-message agent subreports for a decision report.

        Args:
            trace: Joined decision trace artifacts.

        Returns:
            Agent subreport rows.
        """

        return [
            {
                "message_id": str(message.message_id),
                "role": message.role,
                "content": message.content,
                "created_at_sim_time": message.created_at_sim_time.isoformat(),
            }
            for message in trace.messages
        ]

    def _build_decision_report_critic_objections(
        self, trace: DecisionTrace
    ) -> list[dict[str, object]]:
        """Build critic objection rows for a decision report.

        Args:
            trace: Joined decision trace artifacts.

        Returns:
            Critic objection rows.
        """

        return [
            {
                "message_id": str(message.message_id),
                "content": message.content,
                "created_at_sim_time": message.created_at_sim_time.isoformat(),
            }
            for message in trace.messages
            if message.role == "critic"
        ]

    def _build_decision_report_posterior_performance(
        self, reviews: list[DecisionReview]
    ) -> dict[str, object]:
        """Build posterior performance summary for a decision report.

        Args:
            reviews: Posterior decision reviews.

        Returns:
            Posterior performance summary.
        """

        latest_review = reviews[-1] if reviews else None
        return {
            "review_count": len(reviews),
            "correct_direction_count": sum(
                1 for review in reviews if review.was_correct_directionally
            ),
            "error_tags": sorted(
                {tag for review in reviews for tag in review.error_tags}
            ),
            "latest": (
                {
                    "review_id": str(latest_review.review_id),
                    "horizon": latest_review.horizon,
                    "realized_return": str(latest_review.realized_return),
                    "max_adverse_excursion": str(latest_review.max_adverse_excursion),
                    "max_favorable_excursion": str(
                        latest_review.max_favorable_excursion
                    ),
                    "was_correct_directionally": (
                        latest_review.was_correct_directionally
                    ),
                }
                if latest_review is not None
                else None
            ),
        }

    def _build_decision_report_review_conclusion(
        self, reviews: list[DecisionReview]
    ) -> str | None:
        """Build the latest posterior review conclusion for a decision report.

        Args:
            reviews: Posterior decision reviews.

        Returns:
            Latest reviewer summary when present.
        """

        latest_review = reviews[-1] if reviews else None
        return latest_review.reviewer_summary if latest_review is not None else None

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
        observation = self._find_decision_observation(state, decision)
        reviews = self.list_decision_reviews(decision_id)
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
                "agent_subreports": (
                    self._build_decision_report_agent_subreports(trace)
                ),
                "observation": (
                    observation.model_dump(mode="json")
                    if observation is not None
                    else None
                ),
                "final_trade_intent": decision.model_dump(mode="json"),
                "critic_objections": (
                    self._build_decision_report_critic_objections(trace)
                ),
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
                "posterior_reviews": [
                    review.model_dump(mode="json") for review in reviews
                ],
                "posterior_performance": (
                    self._build_decision_report_posterior_performance(reviews)
                ),
                "review_conclusion": (
                    self._build_decision_report_review_conclusion(reviews)
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
        realtime_envelope = build_alert_envelope(alert)
        state.realtime_events.append(realtime_envelope)
        if self._repository is not None:
            self._repository.save_alert(alert)
            self._repository.save_realtime_events([realtime_envelope])
        self._publish_realtime_envelopes([realtime_envelope])
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

    def _replace_state_decision(
        self, state: SimulationState, updated_decision: TradeIntent
    ) -> None:
        """Replace one decision in process-local simulation state.

        Args:
            state: Simulation state that owns the decision.
            updated_decision: Replacement decision record.

        Raises:
            KeyError: If the decision is not present in state.
        """

        for index, decision in enumerate(state.decisions):
            if decision.decision_id == updated_decision.decision_id:
                state.decisions[index] = updated_decision
                return
        raise KeyError(updated_decision.decision_id)

    def _publish_realtime_envelopes(
        self,
        envelopes: Sequence[dict[str, object]],
    ) -> None:
        """Publish realtime envelopes for a completed simulation step.

        Args:
            envelopes: Realtime envelopes produced by the step.
        """

        if self._realtime_fanout is None:
            return
        receipts = self._realtime_fanout.publish_many(list(envelopes))
        self._realtime_fanout_receipts.extend(receipts)

    def _require_mapping(
        self, payload: dict[str, object], key: str
    ) -> dict[str, object]:
        """Read a required mapping value from a runtime payload.

        Args:
            payload: Runtime payload.
            key: Required payload key.

        Returns:
            Mapping value.

        Raises:
            ValueError: If the value is missing or not a mapping.
        """

        value = payload.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"Agent inference payload field {key} must be an object.")
        return value

    def _require_mapping_sequence(
        self, payload: dict[str, object], key: str
    ) -> tuple[dict[str, object], ...]:
        """Read a required sequence of mappings from a runtime payload.

        Args:
            payload: Runtime payload.
            key: Required payload key.

        Returns:
            Mapping values.

        Raises:
            ValueError: If the value is missing or not a list of mappings.
        """

        value = payload.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(
                f"Agent inference payload field {key} must be a list of objects."
            )
        return tuple(value)

    def _validate_agent_trace_payload(
        self,
        observation: Observation,
        decision: TradeIntent,
        agent_run: AgentRun,
        messages: Sequence[AgentMessage],
    ) -> None:
        """Validate worker trace artifact linkage.

        Args:
            observation: Source observation snapshot.
            decision: Validated trade intent.
            agent_run: Agent run trace artifact.
            messages: Agent messages for the trace.

        Raises:
            ValueError: If any artifact does not reference the same trace scope.
        """

        if decision.run_id != observation.run_id:
            raise ValueError(
                "Agent inference decision run_id does not match observation."
            )
        if decision.symbol != observation.symbol:
            raise ValueError(
                "Agent inference decision symbol does not match observation."
            )
        if (
            decision.observation_id is not None
            and decision.observation_id != observation.observation_id
        ):
            raise ValueError(
                "Agent inference decision observation_id does not match observation."
            )
        if agent_run.run_id != decision.run_id:
            raise ValueError("Agent run run_id does not match decision.")
        if agent_run.decision_id != decision.decision_id:
            raise ValueError("Agent run decision_id does not match decision.")
        if (
            decision.agent_run_id is not None
            and decision.agent_run_id != agent_run.agent_run_id
        ):
            raise ValueError(
                "Agent inference decision agent_run_id does not match agent run."
            )
        if any(message.agent_run_id != agent_run.agent_run_id for message in messages):
            raise ValueError("Agent message agent_run_id does not match agent run.")

    def _enrich_agent_trace_decision(
        self,
        observation: Observation,
        decision: TradeIntent,
        agent_run: AgentRun,
    ) -> TradeIntent:
        """Attach persisted trace provenance to a worker-provided decision.

        Args:
            observation: Source observation snapshot.
            decision: Worker-provided trade intent.
            agent_run: Worker-provided agent run.

        Returns:
            Trade intent enriched for trace persistence.
        """

        return decision.model_copy(
            update={
                "observation_id": observation.observation_id,
                "agent_run_id": agent_run.agent_run_id,
                "input_data_as_of": observation.as_of,
                "status": "schema_validated",
            }
        )

    def _create_trade_intent(
        self,
        run_id: UUID,
        symbol: str,
        observation_id: UUID,
        confidence: float,
        data_quality_score: float,
        events: Sequence[MarketEvent],
        input_data_as_of: datetime,
        simulated_time: datetime,
    ) -> TradeIntent:
        """Create deterministic synthetic trade intent for a step.

        Args:
            run_id: Simulation run identifier.
            symbol: Symbol for the intent.
            observation_id: Observation snapshot that produced the intent.
            confidence: Synthetic confidence score.
            data_quality_score: Observation data-quality score.
            events: Point-in-time market events included in the observation.
            input_data_as_of: Point-in-time data availability timestamp.
            simulated_time: Simulated decision time.

        Returns:
            Structured trade intent.
        """

        decision_id = uuid4()
        return TradeIntent(
            decision_id=decision_id,
            run_id=run_id,
            observation_id=observation_id,
            agent_run_id=self._build_agent_run_id(decision_id),
            input_data_as_of=input_data_as_of,
            agent_id="synthetic_trader",
            symbol=symbol,
            market_type="synthetic",
            action="open_long",
            target_weight=Decimal("0.10"),
            max_leverage=Decimal("1"),
            confidence=confidence,
            expected_holding_period="1h",
            thesis="Synthetic trend-following seed decision.",
            evidence=self._build_decision_evidence(events),
            invalidation_conditions=["confidence_below_threshold"],
            data_quality_score=data_quality_score,
            created_at_sim_time=simulated_time,
        )

    def _build_decision_evidence(
        self, events: Sequence[MarketEvent]
    ) -> list[dict[str, object]]:
        """Build synthetic decision evidence from point-in-time events.

        Args:
            events: Point-in-time market events included in the observation.

        Returns:
            Decision evidence entries.
        """

        evidence: list[dict[str, object]] = [{"type": "synthetic_candle"}]
        for event in events:
            if event.type == "candle_closed":
                continue
            evidence.append(
                {
                    "type": "market_event",
                    "event_type": event.type,
                    "source": event.source,
                    "confidence": event.confidence,
                    "simulated_time": event.simulated_time.isoformat(),
                    "payload": dict(event.payload),
                }
            )
        return evidence

    def _build_agent_run_id(self, decision_id: UUID) -> UUID:
        """Build the deterministic agent-run identifier for a decision.

        Args:
            decision_id: Source decision identifier.

        Returns:
            Deterministic agent-run identifier.
        """

        return uuid5(NAMESPACE_URL, f"agent-run:{decision_id}")

    def _build_agent_run(self, decision: TradeIntent) -> AgentRun:
        """Build a deterministic agent run for a decision.

        Args:
            decision: Source trade intent.

        Returns:
            Derived agent run.
        """

        return AgentRun(
            agent_run_id=decision.agent_run_id
            or self._build_agent_run_id(decision.decision_id),
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
        ]
        message_specs.extend(
            ("assistant", content)
            for content in self._build_role_trace_contents(decision)
        )
        if self._settings.agent_critic_enabled:
            message_specs.append(
                ("critic", self._build_critic_message_content(decision))
            )
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

    def _build_role_trace_contents(
        self, decision: TradeIntent
    ) -> list[dict[str, object]]:
        """Build deterministic role-specific trace content for a decision.

        Args:
            decision: Source trade intent.

        Returns:
            Ordered assistant-role trace content.
        """

        role_contents: list[dict[str, object]] = []
        if self._settings.agent_coordinator_enabled:
            role_contents.append(
                {
                    "agent_role": "coordinator",
                    "dispatched_roles": self._configured_analysis_role_names(),
                    "aggregation": "final_intent_ready_for_validation",
                    "final_action": decision.action,
                }
            )
        if self._settings.agent_market_regime_enabled:
            role_contents.append(
                {
                    "agent_role": "market_regime",
                    "regime": "synthetic_trend_following",
                    "risk_regime": "simulation_controlled",
                    "confidence": decision.confidence,
                }
            )
        if self._settings.agent_technical_enabled:
            role_contents.append(
                {
                    "agent_role": "technical",
                    "signal": "synthetic_momentum",
                    "target_weight": str(decision.target_weight),
                    "expected_holding_period": decision.expected_holding_period,
                }
            )
        if self._settings.agent_derivatives_enabled:
            role_contents.append(
                {
                    "agent_role": "derivatives",
                    "market_type": decision.market_type,
                    "max_leverage": str(decision.max_leverage),
                    "funding_context": "synthetic_funding",
                }
            )
        if self._settings.agent_event_enabled:
            event_types = self._extract_decision_event_types(decision)
            role_contents.append(
                {
                    "agent_role": "event",
                    "event_evidence_count": len(event_types),
                    "event_types": event_types,
                    "event_shock_detected": self._has_event_shock(event_types),
                    "data_policy": "untrusted_event_text_is_data",
                }
            )
        if self._settings.agent_quant_rl_enabled:
            role_contents.append(
                {
                    "agent_role": "quant_rl",
                    "policy_signal": str(decision.target_weight),
                    "model_id": self._settings.agent_quant_rl_model_id,
                    "advisory_only": True,
                }
            )
        role_contents.append(
            {
                "agent_role": "trader",
                "decision_id": str(decision.decision_id),
                "action": decision.action,
                "confidence": decision.confidence,
                "thesis": decision.thesis,
                "evidence": decision.evidence,
            }
        )
        if self._settings.agent_portfolio_enabled:
            role_contents.append(
                {
                    "agent_role": "portfolio",
                    "target_weight": str(decision.target_weight),
                    "target_notional": (
                        str(decision.target_notional)
                        if decision.target_notional is not None
                        else None
                    ),
                    "max_leverage": str(decision.max_leverage),
                    "pre_risk_review": True,
                }
            )
        return role_contents

    def _extract_decision_event_types(self, decision: TradeIntent) -> list[str]:
        """Extract market event types carried by decision evidence.

        Args:
            decision: Trade intent containing evidence entries.

        Returns:
            Event type names in evidence order.
        """

        event_types: list[str] = []
        for evidence in decision.evidence:
            if evidence.get("type") != "market_event":
                continue
            event_type = evidence.get("event_type")
            if isinstance(event_type, str):
                event_types.append(event_type)
        return event_types

    def _has_event_shock(self, event_types: Sequence[str]) -> bool:
        """Return whether evidence contains an event-shock category.

        Args:
            event_types: Market event type names carried by evidence.

        Returns:
            `True` when any event type represents a shock-like event.
        """

        shock_types = {
            "funding_update",
            "news_event",
            "liquidity_shock",
            "volatility_shock",
            "system_event",
        }
        return any(event_type in shock_types for event_type in event_types)

    def _configured_analysis_role_names(self) -> list[str]:
        """Return enabled advisory role names dispatched by the coordinator.

        Returns:
            Ordered enabled role names.
        """

        roles: list[str] = []
        if self._settings.agent_market_regime_enabled:
            roles.append("market_regime")
        if self._settings.agent_technical_enabled:
            roles.append("technical")
        if self._settings.agent_derivatives_enabled:
            roles.append("derivatives")
        if self._settings.agent_event_enabled:
            roles.append("event")
        if self._settings.agent_quant_rl_enabled:
            roles.append("quant_rl")
        roles.append("trader")
        if self._settings.agent_portfolio_enabled:
            roles.append("portfolio")
        return roles

    def _build_critic_message_content(self, decision: TradeIntent) -> dict[str, object]:
        """Build deterministic critic trace content for one decision.

        Args:
            decision: Source trade intent.

        Returns:
            Critic trace content.
        """

        return {
            "decision_id": str(decision.decision_id),
            "reviewed_action": decision.action,
            "evidence_count": len(decision.evidence),
            "invalidation_conditions": decision.invalidation_conditions,
            "risk_challenges": [
                "Does the evidence support the requested target weight?",
                "Can independent risk review resize or reject this intent?",
            ],
        }
