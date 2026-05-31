"""Plugin registry service with sandbox validation."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.db.repositories import SimulationRepository
from tiko.domain.plugin import PluginManifest, PluginRegistryEntry, PluginStatus
from tiko.plugins import validate_plugin_manifest


class PluginRegistryService:
    """Manage plugin registry entries after sandbox policy validation."""

    def __init__(self, repository: SimulationRepository | None = None) -> None:
        """Initialize the registry service.

        Args:
            repository: Optional persistence repository.
        """

        self._repository = repository
        self._entries: dict[UUID, PluginRegistryEntry] = {}

    def register_plugin(self, manifest: PluginManifest) -> PluginRegistryEntry:
        """Validate and register a plugin manifest.

        Args:
            manifest: Plugin manifest.

        Returns:
            Registered plugin entry.

        Raises:
            ValueError: If sandbox validation fails.
        """

        sandbox_result = validate_plugin_manifest(manifest)
        if not sandbox_result.passed:
            raise ValueError("; ".join(sandbox_result.violations))
        entry = PluginRegistryEntry(
            plugin_id=uuid4(),
            manifest=manifest,
            sandbox_result=sandbox_result,
            status="validated",
            created_at=datetime.now(UTC),
        )
        self._entries[entry.plugin_id] = entry
        if self._repository is not None:
            self._repository.save_plugin_registry_entry(entry)
        return entry

    def list_plugins(self) -> list[PluginRegistryEntry]:
        """List registered plugins.

        Returns:
            Plugin registry entries.
        """

        return sorted(self._entries.values(), key=lambda entry: entry.created_at)

    def get_plugin(self, plugin_id: UUID) -> PluginRegistryEntry:
        """Get one plugin registry entry.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            Plugin registry entry.

        Raises:
            KeyError: If no plugin exists for the ID.
        """

        return self._entries[plugin_id]

    def update_status(
        self, plugin_id: UUID, status: PluginStatus
    ) -> PluginRegistryEntry:
        """Update a plugin registry status.

        Args:
            plugin_id: Plugin identifier.
            status: New plugin status.

        Returns:
            Updated plugin registry entry.

        Raises:
            KeyError: If no plugin exists for the ID.
        """

        entry = self._entries[plugin_id].model_copy(update={"status": status})
        self._entries[plugin_id] = entry
        if self._repository is not None:
            self._repository.save_plugin_registry_entry(entry)
        return entry
