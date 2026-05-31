"""Build point-in-time-safe observations from simulation artifacts."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from tiko.domain.account import Position
from tiko.domain.market import Candle, FeatureSnapshot, MarketEvent, OrderBookSnapshot
from tiko.domain.memory import MemoryEntry
from tiko.domain.observation import Observation
from tiko.domain.risk import RiskLimits
from tiko.domain.simulation import SimulationRun


class ObservationBuilder:
    """Build bounded observations without future market data."""

    def __init__(self, candle_lookback: int = 50) -> None:
        """Initialize observation limits.

        Args:
            candle_lookback: Maximum number of candles retained per observation.

        Raises:
            ValueError: If lookback is not positive.
        """

        if candle_lookback <= 0:
            raise ValueError("Candle lookback must be positive.")
        self._candle_lookback = candle_lookback

    def build(
        self,
        run: SimulationRun,
        symbol: str,
        as_of: datetime,
        candles: Sequence[Candle],
        events: Sequence[MarketEvent] | None = None,
        orderbooks: Sequence[OrderBookSnapshot] | None = None,
        feature_snapshots: Sequence[FeatureSnapshot] | None = None,
        positions: Sequence[Position] | None = None,
        risk_limits: RiskLimits | None = None,
        memory_entries: Sequence[MemoryEntry] | None = None,
        observation_id: UUID | None = None,
    ) -> Observation:
        """Build one point-in-time observation.

        Args:
            run: Simulation run associated with the observation.
            symbol: Symbol to observe.
            as_of: Observation timestamp.
            candles: Candidate candles.
            events: Optional candidate market events.
            orderbooks: Optional candidate order book snapshots.
            feature_snapshots: Optional candidate feature snapshots.
            positions: Optional candidate simulated positions.
            risk_limits: Optional active risk limits.
            memory_entries: Optional candidate memory entries.
            observation_id: Optional stable observation identifier.

        Returns:
            Point-in-time-safe observation.
        """

        selected_candles = self._select_candles(symbol, as_of, candles)
        selected_events = self._select_events(symbol, as_of, events or [])
        selected_orderbook = self._select_orderbook(symbol, as_of, orderbooks or [])
        selected_features = self._select_features(
            run.run_id, symbol, as_of, feature_snapshots or []
        )
        selected_positions = self._select_positions(run, as_of, positions or [])
        selected_memory = self._select_memory(run.run_id, as_of, memory_entries or [])
        return Observation(
            observation_id=observation_id or uuid4(),
            run_id=run.run_id,
            symbol=symbol,
            as_of=as_of,
            account=run.account,
            candles=selected_candles,
            events=selected_events,
            orderbook=selected_orderbook,
            features=selected_features,
            positions=selected_positions,
            risk_limits=risk_limits,
            memory=selected_memory,
        )

    def _select_candles(
        self, symbol: str, as_of: datetime, candles: Sequence[Candle]
    ) -> list[Candle]:
        """Select available candles for one symbol.

        Args:
            symbol: Symbol to observe.
            as_of: Observation timestamp.
            candles: Candidate candles.

        Returns:
            Latest available candles within the lookback limit.
        """

        available_candles = sorted(
            (
                candle
                for candle in candles
                if candle.symbol == symbol and candle.as_of <= as_of
            ),
            key=lambda candle: (candle.as_of, candle.close_time, candle.open_time),
        )
        return available_candles[-self._candle_lookback :]

    def _select_events(
        self, symbol: str, as_of: datetime, events: Sequence[MarketEvent]
    ) -> list[MarketEvent]:
        """Select available events for one symbol.

        Args:
            symbol: Symbol to observe.
            as_of: Observation timestamp.
            events: Candidate events.

        Returns:
            Available events sorted by simulated time.
        """

        return sorted(
            (
                event
                for event in events
                if event.simulated_time <= as_of
                and (event.symbol is None or event.symbol == symbol)
            ),
            key=lambda event: (event.simulated_time, str(event.event_id)),
        )

    def _select_orderbook(
        self,
        symbol: str,
        as_of: datetime,
        orderbooks: Sequence[OrderBookSnapshot],
    ) -> OrderBookSnapshot | None:
        """Select the latest available order book for one symbol.

        Args:
            symbol: Symbol to observe.
            as_of: Observation timestamp.
            orderbooks: Candidate order book snapshots.

        Returns:
            Latest available order book snapshot, or `None`.
        """

        available_orderbooks = sorted(
            (
                orderbook
                for orderbook in orderbooks
                if orderbook.symbol == symbol and orderbook.as_of <= as_of
            ),
            key=lambda orderbook: (orderbook.as_of, orderbook.source),
        )
        return available_orderbooks[-1] if available_orderbooks else None

    def _select_features(
        self,
        run_id: UUID,
        symbol: str,
        as_of: datetime,
        feature_snapshots: Sequence[FeatureSnapshot],
    ) -> dict[str, object]:
        """Select the latest available feature map for one run and symbol.

        Args:
            run_id: Simulation run identifier.
            symbol: Symbol to observe.
            as_of: Observation timestamp.
            feature_snapshots: Candidate feature snapshots.

        Returns:
            Latest available feature map, or an empty mapping.
        """

        available_snapshots = sorted(
            (
                snapshot
                for snapshot in feature_snapshots
                if snapshot.run_id == run_id
                and snapshot.symbol == symbol
                and snapshot.as_of <= as_of
            ),
            key=lambda snapshot: (
                snapshot.as_of,
                snapshot.source,
                str(snapshot.snapshot_id),
            ),
        )
        return dict(available_snapshots[-1].features) if available_snapshots else {}

    def _select_positions(
        self,
        run: SimulationRun,
        as_of: datetime,
        positions: Sequence[Position],
    ) -> list[Position]:
        """Select portfolio positions available before the observation time.

        Args:
            run: Simulation run associated with the observation.
            as_of: Observation timestamp.
            positions: Candidate simulated positions.

        Returns:
            Available account positions sorted by symbol.
        """

        return sorted(
            (
                position
                for position in positions
                if position.account_id == run.account.account_id
                and position.updated_at_sim_time <= as_of
            ),
            key=lambda position: (position.symbol, position.updated_at_sim_time),
        )

    def _select_memory(
        self,
        run_id: UUID,
        as_of: datetime,
        memory_entries: Sequence[MemoryEntry],
    ) -> list[MemoryEntry]:
        """Select memory entries available before the observation time.

        Args:
            run_id: Simulation run identifier.
            as_of: Observation timestamp.
            memory_entries: Candidate memory entries.

        Returns:
            Available memory entries sorted by availability time.
        """

        return sorted(
            (
                entry
                for entry in memory_entries
                if entry.run_id == run_id and entry.available_at_sim_time <= as_of
            ),
            key=lambda entry: (
                entry.available_at_sim_time,
                entry.created_at,
                str(entry.memory_id),
            ),
        )
