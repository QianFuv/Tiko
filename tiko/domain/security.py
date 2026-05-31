"""Security, RBAC, and audit schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

Role = Literal["admin", "researcher", "operator", "viewer"]
Permission = Literal[
    "observe",
    "manage_simulations",
    "manage_research",
    "manage_plugins",
    "manage_reports",
    "manage_alerts",
    "read_audit",
]


class Principal(DomainModel):
    """Represent the current control-plane caller."""

    user_id: str = Field(min_length=1)
    role: Role


class AuditLogEntry(DomainModel):
    """Represent one audited control-plane action."""

    audit_id: UUID
    user_id: str
    role: Role
    action: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    metadata: dict[str, object]
    created_at: datetime
