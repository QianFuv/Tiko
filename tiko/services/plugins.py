"""Plugin registry service with sandbox validation."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiko.db.repositories import SimulationRepository
from tiko.domain.plugin import PluginManifest, PluginRegistryEntry, PluginStatus
from tiko.plugins import run_plugin_sandbox_tests


def build_plugin_manifest_digest(manifest: PluginManifest) -> str:
    """Build a deterministic digest for a plugin manifest.

    Args:
        manifest: Plugin manifest to fingerprint.

    Returns:
        SHA-256 digest of the canonical JSON manifest payload.
    """

    payload = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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

        sandbox_report = run_plugin_sandbox_tests(manifest)
        if not sandbox_report.passed:
            violations = [
                *sandbox_report.validation.violations,
                *[
                    result.message
                    for result in sandbox_report.results
                    if not result.passed
                ],
            ]
            raise ValueError("; ".join(violations))
        entry = PluginRegistryEntry(
            plugin_id=uuid4(),
            manifest=manifest,
            manifest_digest=build_plugin_manifest_digest(manifest),
            sandbox_result=sandbox_report.validation,
            status="validated",
            approved_by=None,
            approved_at=None,
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

        if self._repository is not None:
            return self._repository.list_plugin_registry_entries()
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

        if self._repository is not None:
            entry = self._repository.get_plugin_registry_entry(plugin_id)
            if entry is None:
                raise KeyError(plugin_id)
            return entry
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
            ValueError: If status update would bypass approval.
        """

        if status == "enabled":
            raise ValueError("Use plugin approval to enable plugins.")
        if status not in {"archived", "rejected"}:
            raise ValueError("Plugin status updates only support archived or rejected.")
        entry = self.get_plugin(plugin_id).model_copy(update={"status": status})
        self._entries[plugin_id] = entry
        if self._repository is not None:
            self._repository.save_plugin_registry_entry(entry)
        return entry

    def approve_plugin(
        self, plugin_id: UUID, manifest_digest: str, approved_by: str
    ) -> PluginRegistryEntry:
        """Approve and enable a validated plugin by matching its manifest digest.

        Args:
            plugin_id: Plugin identifier.
            manifest_digest: Expected manifest digest from the approval request.
            approved_by: User identifier approving the plugin.

        Returns:
            Enabled plugin registry entry.

        Raises:
            KeyError: If no plugin exists for the ID.
            ValueError: If the plugin cannot be approved.
        """

        entry = self.get_plugin(plugin_id)
        if entry.status != "validated":
            raise ValueError("Only validated plugins can be approved.")
        if entry.manifest_digest != manifest_digest:
            raise ValueError("manifest_digest does not match registered plugin.")
        approved_entry = entry.model_copy(
            update={
                "status": "enabled",
                "approved_by": approved_by,
                "approved_at": datetime.now(UTC),
            }
        )
        self._entries[plugin_id] = approved_entry
        if self._repository is not None:
            self._repository.save_plugin_registry_entry(approved_entry)
        return approved_entry
