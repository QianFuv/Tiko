"""Experiment registry service for simulated research workflows."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.domain.experiment import ExperimentKind, ExperimentRecord


class ExperimentService:
    """Manage process-local research experiments."""

    def __init__(self) -> None:
        """Initialize the experiment service."""

        self._experiments: dict[UUID, ExperimentRecord] = {}

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

    def queue_run(self, experiment_id: UUID) -> ExperimentRecord:
        """Queue an experiment run without executing heavy work in-process.

        Args:
            experiment_id: Experiment identifier.

        Returns:
            Queued experiment record.

        Raises:
            KeyError: If the experiment does not exist.
        """

        experiment = self._experiments[experiment_id]
        queued_experiment = experiment.model_copy(
            update={
                "status": "queued",
                "queued_at": datetime.now(UTC),
                "metrics": experiment.metrics | {"queued": True},
            }
        )
        self._experiments[experiment_id] = queued_experiment
        return queued_experiment
