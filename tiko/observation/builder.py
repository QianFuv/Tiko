"""Build point-in-time-safe observations from simulation artifacts."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from tiko.domain.market import Candle, MarketEvent
from tiko.domain.observation import Observation
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
        observation_id: UUID | None = None,
    ) -> Observation:
        """Build one point-in-time observation.

        Args:
            run: Simulation run associated with the observation.
            symbol: Symbol to observe.
            as_of: Observation timestamp.
            candles: Candidate candles.
            events: Optional candidate market events.
            observation_id: Optional stable observation identifier.

        Returns:
            Point-in-time-safe observation.
        """

        selected_candles = self._select_candles(symbol, as_of, candles)
        selected_events = self._select_events(symbol, as_of, events or [])
        return Observation(
            observation_id=observation_id or uuid4(),
            run_id=run.run_id,
            symbol=symbol,
            as_of=as_of,
            account=run.account,
            candles=selected_candles,
            events=selected_events,
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
