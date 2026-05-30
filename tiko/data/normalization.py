"""Normalization helpers for read-only candle market data."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from tiko.domain.market import Candle

REQUIRED_CANDLE_FIELDS = frozenset(
    {
        "symbol",
        "timeframe",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
        "as_of",
    }
)

TIMEFRAME_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}


class MarketDataNormalizationError(ValueError):
    """Raised when raw market data cannot be normalized safely."""


def normalize_candle_record(record: Mapping[str, object]) -> Candle:
    """Normalize a mapping into a point-in-time candle domain model.

    Args:
        record: Raw candle mapping with required OHLCV fields.

    Returns:
        Normalized candle.

    Raises:
        MarketDataNormalizationError: If required fields or scalar values are invalid.
    """

    missing_fields = REQUIRED_CANDLE_FIELDS.difference(record)
    if missing_fields:
        missing_text = ", ".join(sorted(missing_fields))
        raise MarketDataNormalizationError(
            f"Candle record is missing required fields: {missing_text}."
        )

    return Candle(
        symbol=parse_string(record["symbol"], "symbol"),
        timeframe=parse_string(record["timeframe"], "timeframe"),
        open_time=parse_datetime(record["open_time"], "open_time"),
        close_time=parse_datetime(record["close_time"], "close_time"),
        open=parse_decimal(record["open"], "open"),
        high=parse_decimal(record["high"], "high"),
        low=parse_decimal(record["low"], "low"),
        close=parse_decimal(record["close"], "close"),
        volume=parse_decimal(record["volume"], "volume"),
        quote_volume=parse_optional_decimal(record.get("quote_volume"), "quote_volume"),
        source=parse_string(record["source"], "source"),
        as_of=parse_datetime(record["as_of"], "as_of"),
        created_at=parse_datetime(
            record.get("created_at", record["as_of"]), "created_at"
        ),
    )


def normalize_ccxt_ohlcv_row(
    row: Sequence[object],
    symbol: str,
    timeframe: str,
    source: str,
    fetched_at: datetime | None = None,
) -> Candle:
    """Normalize a CCXT public OHLCV row into a candle domain model.

    Args:
        row: CCXT OHLCV row in `[timestamp_ms, open, high, low, close, volume]` shape.
        symbol: Market symbol associated with the row.
        timeframe: Candle timeframe associated with the row.
        source: Read-only data source name.
        fetched_at: Optional wall-clock fetch timestamp.

    Returns:
        Normalized candle.

    Raises:
        MarketDataNormalizationError: If the row is incomplete or invalid.
    """

    if len(row) < 6:
        raise MarketDataNormalizationError(
            "CCXT OHLCV rows must include timestamp, open, high, low, close, "
            "and volume."
        )
    open_time = parse_exchange_timestamp(row[0], "timestamp")
    close_time = open_time + parse_timeframe_delta(timeframe)
    created_at = ensure_aware_datetime(fetched_at or datetime.now(UTC))
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=parse_decimal(row[1], "open"),
        high=parse_decimal(row[2], "high"),
        low=parse_decimal(row[3], "low"),
        close=parse_decimal(row[4], "close"),
        volume=parse_decimal(row[5], "volume"),
        quote_volume=None,
        source=source,
        as_of=close_time,
        created_at=created_at,
    )


def parse_string(value: object, field_name: str) -> str:
    """Parse a required string field.

    Args:
        value: Raw value.
        field_name: Field name for errors.

    Returns:
        Non-empty string value.

    Raises:
        MarketDataNormalizationError: If the value is blank.
    """

    parsed_value = str(value).strip()
    if not parsed_value:
        raise MarketDataNormalizationError(f"Field {field_name} cannot be blank.")
    return parsed_value


def parse_decimal(value: object, field_name: str) -> Decimal:
    """Parse a required decimal field without binary float drift.

    Args:
        value: Raw value.
        field_name: Field name for errors.

    Returns:
        Decimal value.

    Raises:
        MarketDataNormalizationError: If the value is missing or invalid.
    """

    if value is None:
        raise MarketDataNormalizationError(f"Field {field_name} is required.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise MarketDataNormalizationError(
            f"Field {field_name} must be a decimal-compatible value."
        ) from error


def parse_optional_decimal(value: object, field_name: str) -> Decimal | None:
    """Parse an optional decimal field.

    Args:
        value: Raw value.
        field_name: Field name for errors.

    Returns:
        Decimal value or `None`.
    """

    if value in (None, ""):
        return None
    return parse_decimal(value, field_name)


def parse_datetime(value: object, field_name: str) -> datetime:
    """Parse a timestamp into a timezone-aware datetime.

    Args:
        value: Raw timestamp value.
        field_name: Field name for errors.

    Returns:
        Timezone-aware datetime.

    Raises:
        MarketDataNormalizationError: If the value cannot be parsed.
    """

    if isinstance(value, datetime):
        return ensure_aware_datetime(value)
    if isinstance(value, int | float):
        return parse_exchange_timestamp(value, field_name)
    if isinstance(value, str):
        try:
            normalized_value = value.replace("Z", "+00:00")
            return ensure_aware_datetime(datetime.fromisoformat(normalized_value))
        except ValueError as error:
            raise MarketDataNormalizationError(
                f"Field {field_name} must be an ISO timestamp."
            ) from error
    raise MarketDataNormalizationError(f"Field {field_name} must be a timestamp.")


def parse_exchange_timestamp(value: object, field_name: str) -> datetime:
    """Parse an exchange timestamp in seconds or milliseconds.

    Args:
        value: Raw timestamp value.
        field_name: Field name for errors.

    Returns:
        Timezone-aware UTC datetime.

    Raises:
        MarketDataNormalizationError: If the value cannot be parsed.
    """

    if not isinstance(value, int | float | str):
        raise MarketDataNormalizationError(
            f"Field {field_name} must be a numeric exchange timestamp."
        )
    try:
        numeric_value = float(value)
    except ValueError as error:
        raise MarketDataNormalizationError(
            f"Field {field_name} must be a numeric exchange timestamp."
        ) from error
    seconds = numeric_value / 1000 if numeric_value >= 10_000_000_000 else numeric_value
    return datetime.fromtimestamp(seconds, UTC)


def parse_timeframe_delta(timeframe: str) -> timedelta:
    """Parse a compact exchange timeframe into a timedelta.

    Args:
        timeframe: Compact timeframe such as `1m`, `5m`, `1h`, `1d`, or `1w`.

    Returns:
        Time delta represented by the timeframe.

    Raises:
        MarketDataNormalizationError: If the timeframe is unsupported.
    """

    if len(timeframe) < 2:
        raise MarketDataNormalizationError(f"Unsupported timeframe: {timeframe}.")
    amount_text = timeframe[:-1]
    unit = timeframe[-1]
    if unit not in TIMEFRAME_UNITS:
        raise MarketDataNormalizationError(f"Unsupported timeframe unit: {unit}.")
    try:
        amount = int(amount_text)
    except ValueError as error:
        raise MarketDataNormalizationError(
            f"Unsupported timeframe amount: {amount_text}."
        ) from error
    if amount <= 0:
        raise MarketDataNormalizationError("Timeframe amount must be positive.")
    return timedelta(**{TIMEFRAME_UNITS[unit]: amount})


def ensure_aware_datetime(value: datetime) -> datetime:
    """Ensure a datetime carries timezone information.

    Args:
        value: Datetime value.

    Returns:
        Timezone-aware datetime.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
