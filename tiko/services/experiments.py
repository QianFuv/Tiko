"""Experiment registry service for simulated research workflows."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.domain.experiment import ExperimentKind, ExperimentRecord
from tiko.domain.reporting import ReportArtifact


class ExperimentService:
    """Manage process-local research experiments."""

    def __init__(self) -> None:
        """Initialize the experiment service."""

        self._experiments: dict[UUID, ExperimentRecord] = {}
        self._reports: dict[UUID, list[ReportArtifact]] = {}

    def create_experiment(
        self,
        name: str,
        kind: ExperimentKind,
        hypothesis: str,
        dataset_id: UUID,
        parameters: dict[str, object],
        model_id: UUID | None = None,
    ) -> ExperimentRecord:
        """Create a draft research experiment.

        Args:
            name: Experiment display name.
            kind: Experiment type.
            hypothesis: Research hypothesis being tested.
            dataset_id: Dataset identifier used by the experiment.
            parameters: Experiment parameter map.
            model_id: Optional model registry identifier.

        Returns:
            Created experiment record.
        """

        experiment = ExperimentRecord(
            experiment_id=uuid4(),
            name=name,
            kind=kind,
            hypothesis=hypothesis,
            dataset_id=dataset_id,
            model_id=model_id,
            parameters=parameters,
            status="draft",
            metrics={},
            created_at=datetime.now(UTC),
        )
        self._experiments[experiment.experiment_id] = experiment
        return experiment

    def list_experiments(self) -> list[ExperimentRecord]:
        """List research experiments.

        Returns:
            Experiment records sorted by creation time.
        """

        return sorted(
            self._experiments.values(), key=lambda experiment: experiment.created_at
        )

    def get_experiment(self, experiment_id: UUID) -> ExperimentRecord:
        """Get one research experiment.

        Args:
            experiment_id: Experiment identifier.

        Returns:
            Experiment record.

        Raises:
            KeyError: If the experiment does not exist.
        """

        return self._experiments[experiment_id]

    def queue_run(
        self, experiment_id: UUID, job_id: UUID | None = None
    ) -> ExperimentRecord:
        """Queue an experiment run without executing heavy work in-process.

        Args:
            experiment_id: Experiment identifier.
            job_id: Optional runtime job identifier.

        Returns:
            Queued experiment record.

        Raises:
            KeyError: If the experiment does not exist.
        """

        experiment = self._experiments[experiment_id]
        metrics = experiment.metrics | {"queued": True}
        if job_id is not None:
            metrics["job_id"] = str(job_id)
        queued_experiment = experiment.model_copy(
            update={
                "status": "queued",
                "queued_at": datetime.now(UTC),
                "metrics": metrics,
            }
        )
        self._experiments[experiment_id] = queued_experiment
        return queued_experiment

    def create_experiment_report(self, experiment_id: UUID) -> ReportArtifact:
        """Create a structured report for one experiment.

        Args:
            experiment_id: Experiment identifier.

        Returns:
            Created experiment report.

        Raises:
            KeyError: If the experiment does not exist.
        """

        experiment = self._experiments[experiment_id]
        created_at = datetime.now(UTC)
        report = ReportArtifact(
            report_id=uuid4(),
            run_id=experiment.experiment_id,
            report_type="experiment",
            title=f"{experiment.name} experiment report",
            summary=f"{experiment.kind} experiment is {experiment.status}.",
            sections={
                "experiment": experiment.model_dump(mode="json"),
                "hypothesis": experiment.hypothesis,
                "parameters": experiment.parameters,
                "status": experiment.status,
                "metrics": experiment.metrics,
                "model_id": str(experiment.model_id)
                if experiment.model_id is not None
                else None,
            },
            created_at_sim_time=experiment.queued_at
            or experiment.completed_at
            or experiment.created_at,
            created_at=created_at,
        )
        self._reports.setdefault(experiment_id, []).append(report)
        return report

    def list_experiment_reports(self, experiment_id: UUID) -> list[ReportArtifact]:
        """List reports for one experiment.

        Args:
            experiment_id: Experiment identifier.

        Returns:
            Experiment reports.

        Raises:
            KeyError: If the experiment does not exist.
        """

        self.get_experiment(experiment_id)
        return list(self._reports.get(experiment_id, []))

    def get_report(self, report_id: UUID) -> ReportArtifact:
        """Get one experiment report by ID.

        Args:
            report_id: Report identifier.

        Returns:
            Experiment report.

        Raises:
            KeyError: If the report does not exist.
        """

        for reports in self._reports.values():
            for report in reports:
                if report.report_id == report_id:
                    return report
        raise KeyError(report_id)
