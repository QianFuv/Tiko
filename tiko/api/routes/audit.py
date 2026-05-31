"""Audit log routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from tiko.api.dependencies import get_audit_service, require_permission
from tiko.domain.security import AuditLogEntry, Principal
from tiko.services import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ReadAuditPrincipalDep = Annotated[Principal, Depends(require_permission("read_audit"))]


@router.get("/logs", response_model=list[AuditLogEntry])
def list_audit_logs(
    service: AuditServiceDep,
    principal: ReadAuditPrincipalDep,
) -> list[AuditLogEntry]:
    """List control-plane audit logs.

    Args:
        service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Audit log entries.
    """

    return service.list_entries()
