"""Model registry service for research artifacts."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.db.repositories import SimulationRepository
from tiko.domain.model import ModelRegistryEntry, ModelStatus, ModelType


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

        entry = self._entries[model_id].model_copy(update={"status": status})
        self._entries[model_id] = entry
        if self._repository is not None:
            self._repository.save_model_registry_entry(entry)
        return entry
