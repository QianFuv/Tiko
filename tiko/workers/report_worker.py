"""Report generation worker process definition."""

from pathlib import Path

from tiko.domain.reporting import ReportArtifact
from tiko.domain.runtime import BackgroundJob
from tiko.services.artifacts import ReportArtifactStore
from tiko.services.reports import ReportRenderService
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


def handle_report_generation_job(job: BackgroundJob) -> dict[str, object]:
    """Render and store one report generation job.

    Args:
        job: Claimed report generation job.

    Returns:
        Structured report artifact metadata.

    Raises:
        ValueError: If the job type or payload is invalid.
    """

    if job.job_type != "report_generation":
        raise ValueError("Report worker can only handle report_generation jobs.")
    report = ReportArtifact.model_validate(_require_mapping(job.payload, "report"))
    artifact_root = _optional_artifact_root(job.payload)
    rendered_report = ReportRenderService().render(report)
    stored_artifact = ReportArtifactStore(artifact_root).store(rendered_report)
    return {
        "message": "Report worker rendered and stored report artifact.",
        "job_type": job.job_type,
        "resource_type": job.resource_type,
        "resource_id": job.resource_id,
        "report_id": str(report.report_id),
        "format": rendered_report.format,
        "artifact": stored_artifact.model_dump(mode="json"),
    }


def _require_mapping(
    payload: dict[str, object],
    key: str,
) -> dict[str, object]:
    """Read a required mapping from a job payload.

    Args:
        payload: Runtime job payload.
        key: Required payload key.

    Returns:
        Mapping value.

    Raises:
        ValueError: If the value is missing or not a mapping.
    """

    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Report generation payload field {key} must be an object.")
    return value


def _optional_artifact_root(payload: dict[str, object]) -> str | Path:
    """Read the optional artifact root from a job payload.

    Args:
        payload: Runtime job payload.

    Returns:
        Artifact root path string.

    Raises:
        ValueError: If the value is present but invalid.
    """

    value = payload.get("artifact_root", ".tiko/artifacts")
    if not isinstance(value, str) or not value:
        raise ValueError("Report generation payload field artifact_root is invalid.")
    return value
