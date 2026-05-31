"""Backtest worker process definition."""

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
