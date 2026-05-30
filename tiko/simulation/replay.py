"""Deterministic replay over normalized market candles."""

from collections.abc import Sequence
from datetime import datetime

from tiko.domain.market import Candle


class MarketReplayExhausted(RuntimeError):
    """Raised when a market replay has no remaining candles."""


class MarketReplay:
    """Emit normalized candles in point-in-time replay order."""

    def __init__(self, candles: Sequence[Candle], symbols: Sequence[str]) -> None:
        """Initialize a deterministic candle replay.

        Args:
            candles: Normalized candles available to replay.
            symbols: Symbols included in the simulation run.

        Raises:
            ValueError: If no candles match the requested symbols.
        """

        symbol_set = set(symbols)
        selected_candles = [
            candle
            for candle in candles
            if not symbol_set or candle.symbol in symbol_set
        ]
        if not selected_candles:
            raise ValueError("Market replay requires at least one matching candle.")
        self._candles = tuple(
            sorted(
                selected_candles,
                key=lambda candle: (candle.as_of, candle.close_time, candle.symbol),
            )
        )
        self._index = 0

    def has_next(self) -> bool:
        """Return whether replay has another candle.

        Returns:
            `True` when another candle can be emitted.
        """

        return self._index < len(self._candles)

    def remaining(self) -> int:
        """Return the number of candles not yet emitted.

        Returns:
            Remaining candle count.
        """

        return len(self._candles) - self._index

    def start_time(self) -> datetime:
        """Return the initial simulated time implied by the replay.

        Returns:
            Open time of the first replay candle.
        """

        return self._candles[0].open_time

    def next_candle(self) -> Candle:
        """Return the next candle in replay order.

        Returns:
            Next normalized candle.

        Raises:
            MarketReplayExhausted: If no candles remain.
        """

        if not self.has_next():
            raise MarketReplayExhausted("Market replay has no remaining candles.")
        candle = self._candles[self._index]
        self._index += 1
        return candle
