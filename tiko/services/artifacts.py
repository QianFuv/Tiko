"""Local artifact storage services."""

from datetime import UTC, datetime
from pathlib import Path

from tiko.domain.reporting import RenderedReport, StoredReportArtifact


class ReportArtifactStore:
    """Store rendered report artifacts through a local object-store adapter."""

    def __init__(self, artifact_root: str | Path) -> None:
        """Initialize the report artifact store.

        Args:
            artifact_root: Root directory for local artifacts.
        """

        self._artifact_root = Path(artifact_root)

    def store(self, report: RenderedReport) -> StoredReportArtifact:
        """Store one rendered report artifact.

        Args:
            report: Rendered report document.

        Returns:
            Stored artifact metadata.
        """

        suffix = ".md" if report.format == "markdown" else f".{report.format}"
        artifact_path = self._artifact_root / "reports" / f"{report.report_id}{suffix}"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(report.content.encode("utf-8"))
        return StoredReportArtifact(
            report_id=report.report_id,
            report_type=report.report_type,
            format=report.format,
            artifact_uri=artifact_path.resolve().as_uri(),
            size_bytes=artifact_path.stat().st_size,
            stored_at=datetime.now(UTC),
        )
