"""Local artifact storage services."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from tiko.domain.model import ModelType, StoredModelArtifact
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


class ModelArtifactStore:
    """Store model research artifacts through a local object-store adapter."""

    def __init__(self, artifact_root: str | Path) -> None:
        """Initialize the model artifact store.

        Args:
            artifact_root: Root directory for local artifacts.
        """

        self._artifact_root = Path(artifact_root)

    def store_json_artifact(
        self,
        artifact_id: UUID,
        model_type: ModelType,
        algorithm: str,
        payload: dict[str, object],
    ) -> StoredModelArtifact:
        """Store one model artifact JSON payload.

        Args:
            artifact_id: Stable artifact identifier.
            model_type: Model artifact type.
            algorithm: Training or inference algorithm name.
            payload: JSON-serializable artifact payload.

        Returns:
            Stored model artifact metadata.
        """

        artifact_path = self._artifact_root / "models" / f"{artifact_id}.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(
            json.dumps(payload, default=str, indent=2, sort_keys=True).encode("utf-8")
        )
        return StoredModelArtifact(
            artifact_id=artifact_id,
            model_type=model_type,
            algorithm=algorithm,
            artifact_uri=artifact_path.resolve().as_uri(),
            size_bytes=artifact_path.stat().st_size,
            stored_at=datetime.now(UTC),
        )
