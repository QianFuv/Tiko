"""Reinforcement learning worker process definition."""

from tiko.workers.definitions import WorkerDefinition


def build_definition() -> WorkerDefinition:
    """Build the reinforcement learning worker definition.

    Returns:
        Reinforcement learning worker definition.
    """

    return WorkerDefinition(
        worker_name="rl-worker",
        job_types=("rl_training",),
        description="Runs reinforcement learning training jobs.",
    )
