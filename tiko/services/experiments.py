"""Experiment registry service for simulated research workflows."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.db.repositories import SimulationRepository
from tiko.domain.experiment import ExperimentKind, ExperimentRecord
from tiko.domain.reporting import ReportArtifact
from tiko.domain.runtime import BackgroundJob


class ExperimentService:
    """Manage research experiments with optional repository persistence."""

    def __init__(self, repository: SimulationRepository | None = None) -> None:
        """Initialize the experiment service.

        Args:
            repository: Optional persistence repository.
        """

        self._repository = repository
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
        if self._repository is not None:
            self._repository.save_experiment(experiment)
        return experiment

    def list_experiments(self) -> list[ExperimentRecord]:
        """List research experiments.

        Returns:
            Experiment records sorted by creation time.
        """

        if self._repository is not None:
            return self._repository.list_experiments()
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

        if self._repository is not None:
            experiment = self._repository.get_experiment(experiment_id)
            if experiment is None:
                raise KeyError(experiment_id)
            return experiment
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

        experiment = self.get_experiment(experiment_id)
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
        if self._repository is not None:
            self._repository.save_experiment(queued_experiment)
        return queued_experiment

    def complete_run(
        self,
        experiment_id: UUID,
        metrics: dict[str, object],
        job_id: UUID | None = None,
    ) -> ExperimentRecord:
        """Mark an experiment run as completed.

        Args:
            experiment_id: Experiment identifier.
            metrics: Result metrics to merge into the experiment record.
            job_id: Optional runtime job identifier.

        Returns:
            Completed experiment record.

        Raises:
            KeyError: If the experiment does not exist.
        """

        experiment = self.get_experiment(experiment_id)
        merged_metrics = experiment.metrics | metrics | {"completed": True}
        if job_id is not None:
            merged_metrics["job_id"] = str(job_id)
        completed_experiment = experiment.model_copy(
            update={
                "status": "completed",
                "completed_at": datetime.now(UTC),
                "metrics": merged_metrics,
            }
        )
        self._experiments[experiment_id] = completed_experiment
        if self._repository is not None:
            self._repository.save_experiment(completed_experiment)
        return completed_experiment

    def fail_run(
        self,
        experiment_id: UUID,
        error_message: str,
        job_id: UUID | None = None,
    ) -> ExperimentRecord:
        """Mark an experiment run as failed.

        Args:
            experiment_id: Experiment identifier.
            error_message: Runtime failure reason.
            job_id: Optional runtime job identifier.

        Returns:
            Failed experiment record.

        Raises:
            KeyError: If the experiment does not exist.
        """

        experiment = self.get_experiment(experiment_id)
        merged_metrics = experiment.metrics | {
            "failed": True,
            "error_message": error_message,
        }
        if job_id is not None:
            merged_metrics["job_id"] = str(job_id)
        failed_experiment = experiment.model_copy(
            update={
                "status": "failed",
                "completed_at": datetime.now(UTC),
                "metrics": merged_metrics,
            }
        )
        self._experiments[experiment_id] = failed_experiment
        if self._repository is not None:
            self._repository.save_experiment(failed_experiment)
        return failed_experiment

    def apply_runtime_job(self, job: BackgroundJob) -> ExperimentRecord:
        """Apply a finished experiment runtime job to experiment state.

        Args:
            job: Completed or failed experiment runtime job.

        Returns:
            Updated experiment record.

        Raises:
            ValueError: If the job does not represent a finished experiment run.
            KeyError: If the experiment does not exist.
        """

        if job.job_type != "experiment_run" or job.resource_type != "experiment":
            raise ValueError("Only experiment_run jobs can update experiments.")
        if job.status == "completed":
            return self.complete_run(
                UUID(job.resource_id),
                metrics=self._build_runtime_result_metrics(job.result),
                job_id=job.job_id,
            )
        if job.status == "failed":
            return self.fail_run(
                UUID(job.resource_id),
                error_message=job.error_message
                or "Runtime job failed without an error message.",
                job_id=job.job_id,
            )
        raise ValueError("Only completed or failed experiment_run jobs can be applied.")

    def _build_runtime_result_metrics(
        self, result: dict[str, object]
    ) -> dict[str, object]:
        """Build experiment metrics from a runtime job result.

        Args:
            result: Runtime job result payload.

        Returns:
            Experiment metrics to merge.
        """

        metrics: dict[str, object] = {"runtime_result": result}
        for key in ("backtest_summary", "returns_by_symbol"):
            if key in result:
                metrics[key] = result[key]
        return metrics

    def create_experiment_report(self, experiment_id: UUID) -> ReportArtifact:
        """Create a structured report for one experiment.

        Args:
            experiment_id: Experiment identifier.

        Returns:
            Created experiment report.

        Raises:
            KeyError: If the experiment does not exist.
        """

        experiment = self.get_experiment(experiment_id)
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
        if self._repository is not None:
            self._repository.save_report(report)
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
        if self._repository is not None:
            return [
                report
                for report in self._repository.list_reports(experiment_id)
                if report.report_type == "experiment"
            ]
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

        if self._repository is not None:
            report = self._repository.get_report(report_id)
            if report is not None and report.report_type == "experiment":
                return report
            raise KeyError(report_id)
        for reports in self._reports.values():
            for report in reports:
                if report.report_id == report_id:
                    return report
        raise KeyError(report_id)
