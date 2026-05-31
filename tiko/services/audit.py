"""Audit log service for control-plane actions."""

from datetime import UTC, datetime
from uuid import uuid4

from tiko.db.repositories import SimulationRepository
from tiko.domain.security import AuditLogEntry, Principal


class AuditService:
    """Store process-local audit log entries."""

    def __init__(self, repository: SimulationRepository | None = None) -> None:
        """Initialize an audit log service.

        Args:
            repository: Optional repository for durable audit log storage.
        """

        self._repository = repository
        self._entries: list[AuditLogEntry] = []

    def record(
        self,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, object] | None = None,
    ) -> AuditLogEntry:
        """Record a successful control-plane action.

        Args:
            principal: Caller principal.
            action: Action name.
            resource_type: Resource category.
            resource_id: Resource identifier.
            metadata: Optional structured metadata.

        Returns:
            Created audit log entry.
        """

        entry = AuditLogEntry(
            audit_id=uuid4(),
            user_id=principal.user_id,
            role=principal.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            created_at=datetime.now(UTC),
        )
        self._entries.append(entry)
        if self._repository is not None:
            self._repository.save_audit_log_entry(entry)
        return entry

    def list_entries(self) -> list[AuditLogEntry]:
        """List audit log entries.

        Returns:
            Audit log entries in creation order.
        """

        if self._repository is not None:
            return self._repository.list_audit_log_entries()
        return list(self._entries)
