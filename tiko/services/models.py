"""Model registry service for research artifacts."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from tiko.db.repositories import SimulationRepository
from tiko.domain.model import ModelRegistryEntry, ModelStatus, ModelType
from tiko.domain.rl import RlPolicySignal


class ModelRegistryService:
    """Manage model registry entries with optional persistence."""

    def __init__(self, repository: SimulationRepository | None = None) -> None:
        """Initialize the registry service.

        Args:
            repository: Optional persistence repository.
        """

        self._repository = repository
        self._entries: dict[UUID, ModelRegistryEntry] = {}

    def register_model(
        self,
        name: str,
        version: str,
        model_type: ModelType,
        algorithm: str,
        training_dataset_id: UUID,
        validation_dataset_id: UUID,
        metrics: dict[str, object],
        artifact_uri: str,
        status: ModelStatus = "draft",
    ) -> ModelRegistryEntry:
        """Register a model artifact for research review.

        Args:
            name: Model name.
            version: Model version.
            model_type: Model type.
            algorithm: Algorithm name.
            training_dataset_id: Training dataset identifier.
            validation_dataset_id: Validation dataset identifier.
            metrics: Evaluation metrics.
            artifact_uri: Artifact storage URI.
            status: Initial registry status.

        Returns:
            Registered model entry.
        """

        entry = ModelRegistryEntry(
            model_id=uuid4(),
            name=name,
            version=version,
            model_type=model_type,
            algorithm=algorithm,
            training_dataset_id=training_dataset_id,
            validation_dataset_id=validation_dataset_id,
            metrics=metrics,
            artifact_uri=artifact_uri,
            status=status,
            created_at=datetime.now(UTC),
        )
        self._entries[entry.model_id] = entry
        if self._repository is not None:
            self._repository.save_model_registry_entry(entry)
        return entry

    def list_models(self) -> list[ModelRegistryEntry]:
        """List registered model entries.

        Returns:
            Model registry entries.
        """

        if self._repository is not None:
            return self._repository.list_model_registry_entries()
        return sorted(self._entries.values(), key=lambda entry: entry.created_at)

    def get_model(self, model_id: UUID) -> ModelRegistryEntry:
        """Get one model registry entry.

        Args:
            model_id: Model identifier.

        Returns:
            Model registry entry.

        Raises:
            KeyError: If no model exists for the ID.
        """

        if self._repository is not None:
            entry = self._repository.get_model_registry_entry(model_id)
            if entry is None:
                raise KeyError(model_id)
            return entry
        return self._entries[model_id]

    def update_status(self, model_id: UUID, status: ModelStatus) -> ModelRegistryEntry:
        """Update one model registry status.

        Args:
            model_id: Model identifier.
            status: New registry status.

        Returns:
            Updated model registry entry.

        Raises:
            KeyError: If no model exists for the ID.
        """

        entry = self.get_model(model_id).model_copy(update={"status": status})
        self._entries[model_id] = entry
        if self._repository is not None:
            self._repository.save_model_registry_entry(entry)
        return entry

    def promote_model(self, model_id: UUID) -> ModelRegistryEntry:
        """Promote a model for simulated paper-enabled eligibility.

        Args:
            model_id: Model identifier.

        Returns:
            Promoted model registry entry.

        Raises:
            KeyError: If no model exists for the ID.
        """

        return self.update_status(model_id, "paper_enabled")

    def archive_model(self, model_id: UUID) -> ModelRegistryEntry:
        """Archive a model registry entry.

        Args:
            model_id: Model identifier.

        Returns:
            Archived model registry entry.

        Raises:
            KeyError: If no model exists for the ID.
        """

        return self.update_status(model_id, "archived")

    def serve_policy_signal(self, model_id: UUID) -> RlPolicySignal:
        """Serve an advisory policy signal from a paper-enabled RL model.

        Args:
            model_id: Model identifier.

        Returns:
            Advisory RL policy signal.

        Raises:
            KeyError: If no model exists for the ID.
            ValueError: If the model is not eligible for serving.
        """

        entry = self.get_model(model_id)
        if entry.status != "paper_enabled":
            raise ValueError("Only paper-enabled models can serve policy signals.")
        if entry.model_type != "rl":
            raise ValueError("Only RL models can serve policy signals.")
        action_id = self._required_int_metric(entry.metrics, "best_action_id")
        target_weight = self._required_decimal_metric(
            entry.metrics,
            "best_target_weight",
        )
        return RlPolicySignal(
            model_id=entry.model_id,
            algorithm=entry.algorithm,
            action_id=action_id,
            target_weight=target_weight,
            status="served",
            source="model_registry",
            rationale=(
                "Served best static advisory action from a paper-enabled "
                "model registry entry."
            ),
        )

    def _required_int_metric(self, metrics: dict[str, object], key: str) -> int:
        """Read a required integer metric.

        Args:
            metrics: Model registry metric payload.
            key: Required metric key.

        Returns:
            Parsed integer value.

        Raises:
            ValueError: If the metric is missing or invalid.
        """

        value = metrics.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError as error:
                raise ValueError(f"Metric {key} must be an integer.") from error
        raise ValueError(f"Metric {key} must be an integer.")

    def _required_decimal_metric(self, metrics: dict[str, object], key: str) -> Decimal:
        """Read a required decimal metric.

        Args:
            metrics: Model registry metric payload.
            key: Required metric key.

        Returns:
            Parsed decimal value.

        Raises:
            ValueError: If the metric is missing or invalid.
        """

        value = metrics.get(key)
        if isinstance(value, bool) or value is None:
            raise ValueError(f"Metric {key} must be a decimal.")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"Metric {key} must be a decimal.") from error
