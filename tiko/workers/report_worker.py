"""Report generation worker process definition."""

from tiko.workers.definitions import WorkerDefinition


def build_definition() -> WorkerDefinition:
    """Build the report worker definition.

    Returns:
        Report worker definition.
    """

    return WorkerDefinition(
        worker_name="report-worker",
        job_types=("report_generation",),
        description="Generates simulation, decision, and experiment reports.",
    )
