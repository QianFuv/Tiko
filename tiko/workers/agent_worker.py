"""Agent inference worker process definition."""

from tiko.workers.definitions import WorkerDefinition


def build_definition() -> WorkerDefinition:
    """Build the agent worker definition.

    Returns:
        Agent worker definition.
    """

    return WorkerDefinition(
        worker_name="agent-worker",
        job_types=("agent_inference",),
        description="Runs agent inference outside request handlers.",
    )
