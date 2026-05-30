"""Validation reports for normalized market data."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tiko.domain.market import Candle

ValidationSeverity = Literal["error", "warning"]


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
        for index, candle in enumerate(candles):
            issues.extend(self._validate_candle(index, candle))
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
