"""Validation reports for normalized market data."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from tiko.domain.market import Candle

ValidationSeverity = Literal["error", "warning"]
TIMEFRAME_UNIT_DURATIONS = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}


@dataclass(frozen=True)
class MarketDataValidationIssue:
    """Describe one market data validation finding."""

    index: int
    severity: ValidationSeverity
    code: str
    message: str
    symbol: str
    open_time: str


@dataclass(frozen=True)
class MarketDataValidationReport:
    """Summarize validation findings for a candle sequence."""

    total_records: int
    issues: tuple[MarketDataValidationIssue, ...]

    def has_errors(self) -> bool:
        """Return whether the report contains at least one error.

        Returns:
            `True` when any issue severity is `error`.
        """

        return any(issue.severity == "error" for issue in self.issues)

    def error_count(self) -> int:
        """Return the number of error findings.

        Returns:
            Error count.
        """

        return sum(1 for issue in self.issues if issue.severity == "error")


class MarketDataValidator:
    """Validate normalized candle records for point-in-time safety."""

    def validate_candles(self, candles: Sequence[Candle]) -> MarketDataValidationReport:
        """Validate a candle sequence.

        Args:
            candles: Normalized candles.

        Returns:
            Validation report with errors and warnings.
        """

        issues: list[MarketDataValidationIssue] = []
        seen_keys: set[tuple[str, str, str]] = set()
        previous_by_stream: dict[tuple[str, str], Candle] = {}
        for index, candle in enumerate(candles):
            issues.extend(self._validate_candle(index, candle))
            issues.extend(self._validate_timeframe_duration(index, candle))
            key = (candle.symbol, candle.timeframe, candle.open_time.isoformat())
            if key in seen_keys:
                issues.append(
                    self._create_issue(
                        index=index,
                        candle=candle,
                        severity="error",
                        code="duplicate_candle",
                        message=(
                            "Candle symbol, timeframe, and open_time are duplicated."
                        ),
                    )
                )
            seen_keys.add(key)
            stream_key = (candle.symbol, candle.timeframe)
            previous_candle = previous_by_stream.get(stream_key)
            if previous_candle is not None:
                issues.extend(
                    self._validate_stream_sequence(index, previous_candle, candle)
                )
            previous_by_stream[stream_key] = candle
        return MarketDataValidationReport(
            total_records=len(candles), issues=tuple(issues)
        )

    def _validate_candle(
        self, index: int, candle: Candle
    ) -> list[MarketDataValidationIssue]:
        """Validate one candle.

        Args:
            index: Candle index in the input sequence.
            candle: Candle to validate.

        Returns:
            Validation issues for the candle.
        """

        issues: list[MarketDataValidationIssue] = []
        if candle.open_time >= candle.close_time:
            issues.append(
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="invalid_time_range",
                    message="Candle open_time must be before close_time.",
                )
            )
        if candle.high < max(candle.open, candle.close):
            issues.append(
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="high_below_body",
                    message=(
                        "Candle high must be greater than or equal to open and close."
                    ),
                )
            )
        if candle.low > min(candle.open, candle.close):
            issues.append(
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="low_above_body",
                    message="Candle low must be less than or equal to open and close.",
                )
            )
        if candle.as_of < candle.close_time:
            issues.append(
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="as_of_before_close",
                    message="Candle as_of must not be before close_time.",
                )
            )
        return issues

    def _validate_timeframe_duration(
        self, index: int, candle: Candle
    ) -> list[MarketDataValidationIssue]:
        """Validate that a candle's time range matches its timeframe.

        Args:
            index: Candle index in the input sequence.
            candle: Candle to validate.

        Returns:
            Validation issues for timeframe interpretation.
        """

        duration = self._parse_timeframe_duration(candle.timeframe)
        if duration is None:
            return [
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="warning",
                    code="unknown_timeframe",
                    message="Candle timeframe is not a supported fixed duration.",
                )
            ]
        if candle.close_time - candle.open_time != duration:
            return [
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="timeframe_duration_mismatch",
                    message="Candle close_time does not match timeframe duration.",
                )
            ]
        return []

    def _validate_stream_sequence(
        self,
        index: int,
        previous_candle: Candle,
        candle: Candle,
    ) -> list[MarketDataValidationIssue]:
        """Validate sequence continuity within one symbol and timeframe stream.

        Args:
            index: Candle index in the input sequence.
            previous_candle: Previous candle for the same stream.
            candle: Current candle for the same stream.

        Returns:
            Validation issues for stream ordering and continuity.
        """

        if candle.open_time == previous_candle.open_time:
            return []
        if candle.open_time < previous_candle.open_time:
            return [
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="out_of_order_candle",
                    message="Candle open_time moved backwards within the stream.",
                )
            ]
        if candle.open_time < previous_candle.close_time:
            return [
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="error",
                    code="overlapping_candle",
                    message="Candle open_time overlaps the previous candle close_time.",
                )
            ]
        if candle.open_time > previous_candle.close_time:
            return [
                self._create_issue(
                    index=index,
                    candle=candle,
                    severity="warning",
                    code="candle_gap",
                    message="Candle stream has a gap before this open_time.",
                )
            ]
        return []

    def _parse_timeframe_duration(self, timeframe: str) -> timedelta | None:
        """Parse a fixed candle timeframe into a duration.

        Args:
            timeframe: Candle timeframe such as `1m`, `5m`, `1h`, `1d`, or `1w`.

        Returns:
            Timeframe duration or `None` when unsupported.
        """

        if len(timeframe) < 2:
            return None
        quantity_text = timeframe[:-1]
        unit = timeframe[-1].lower()
        unit_duration = TIMEFRAME_UNIT_DURATIONS.get(unit)
        if unit_duration is None or not quantity_text.isdecimal():
            return None
        quantity = int(quantity_text)
        if quantity <= 0:
            return None
        return unit_duration * quantity

    def _create_issue(
        self,
        index: int,
        candle: Candle,
        severity: ValidationSeverity,
        code: str,
        message: str,
    ) -> MarketDataValidationIssue:
        """Create a validation issue for a candle.

        Args:
            index: Candle index in the input sequence.
            candle: Candle associated with the issue.
            severity: Issue severity.
            code: Stable validation code.
            message: Human-readable validation message.

        Returns:
            Validation issue.
        """

        return MarketDataValidationIssue(
            index=index,
            severity=severity,
            code=code,
            message=message,
            symbol=candle.symbol,
            open_time=candle.open_time.isoformat(),
        )
