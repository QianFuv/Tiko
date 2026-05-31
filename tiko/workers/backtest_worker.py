"""Backtest worker process definition."""

from decimal import Decimal

from tiko.domain.market import Candle
from tiko.domain.runtime import BackgroundJob
from tiko.workers.definitions import WorkerDefinition


def build_definition() -> WorkerDefinition:
    """Build the backtest worker definition.

    Returns:
        Backtest worker definition.
    """

    return WorkerDefinition(
        worker_name="backtest-worker",
        job_types=("backtest", "experiment_run"),
        description="Runs backtests and queued experiment jobs.",
    )


def handle_backtest_job(job: BackgroundJob) -> dict[str, object]:
    """Run a deterministic candle-summary backtest job.

    Args:
        job: Claimed backtest or experiment job.

    Returns:
        Structured backtest summary metadata.

    Raises:
        ValueError: If the job type or payload is invalid.
    """

    if job.job_type not in {"backtest", "experiment_run"}:
        raise ValueError("Backtest worker can only handle backtest jobs.")
    candles = [
        Candle.model_validate(item)
        for item in _require_mapping_sequence(job.payload, "candles")
    ]
    if len(candles) == 0:
        raise ValueError("Backtest payload requires at least one candle.")
    summary = _summarize_candles(candles)
    return {
        "message": "Backtest worker completed deterministic candle summary.",
        "job_type": job.job_type,
        "resource_type": job.resource_type,
        "resource_id": job.resource_id,
        "dataset_id": job.payload.get("dataset_id"),
        "experiment_id": job.payload.get("experiment_id"),
        "kind": job.payload.get("kind", job.job_type),
        "parameters": job.payload.get("parameters", {}),
        "backtest_summary": summary,
        "returns_by_symbol": summary["returns_by_symbol"],
    }


def _require_mapping_sequence(
    payload: dict[str, object],
    key: str,
) -> tuple[dict[str, object], ...]:
    """Read a required sequence of mappings from a job payload.

    Args:
        payload: Runtime job payload.
        key: Required payload key.

    Returns:
        Mapping values.

    Raises:
        ValueError: If the value is missing or not a sequence of mappings.
    """

    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Backtest payload field {key} must be a list of objects.")
    return tuple(value)


def _summarize_candles(candles: list[Candle]) -> dict[str, object]:
    """Build deterministic summary metrics from candles.

    Args:
        candles: Validated candles.

    Returns:
        Backtest summary metrics.
    """

    candles_by_symbol: dict[str, list[Candle]] = {}
    for candle in candles:
        candles_by_symbol.setdefault(candle.symbol, []).append(candle)
    returns_by_symbol = {
        symbol: str(_calculate_total_return(symbol_candles))
        for symbol, symbol_candles in sorted(candles_by_symbol.items())
    }
    return {
        "candle_count": len(candles),
        "symbols": sorted(candles_by_symbol),
        "start_time": min(candle.open_time for candle in candles).isoformat(),
        "end_time": max(candle.close_time for candle in candles).isoformat(),
        "returns_by_symbol": returns_by_symbol,
    }


def _calculate_total_return(candles: list[Candle]) -> Decimal:
    """Calculate first-close to last-close return for one symbol.

    Args:
        candles: Candles for one symbol.

    Returns:
        Total close-to-close return.
    """

    ordered_candles = sorted(candles, key=lambda candle: candle.open_time)
    first_close = ordered_candles[0].close
    last_close = ordered_candles[-1].close
    if first_close == Decimal("0"):
        return Decimal("0")
    return (last_close - first_close) / first_close
