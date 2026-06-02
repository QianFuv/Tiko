"""Plugin registry routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_plugin_registry_service,
    require_permission,
)
from tiko.domain.plugin import (
    PluginManifest,
    PluginRegistryEntry,
    PluginStatus,
    SandboxTestReport,
)
from tiko.domain.security import Principal
from tiko.plugins import run_plugin_sandbox_tests
from tiko.services import AuditService, PluginRegistryService

router = APIRouter(prefix="/plugins", tags=["plugins"])
PluginRegistryServiceDep = Annotated[
    PluginRegistryService, Depends(get_plugin_registry_service)
]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManagePluginsPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_plugins"))
]


class PluginStatusUpdateRequest(BaseModel):
    """Represent a plugin registry status update request."""

    status: PluginStatus


class PluginApprovalRequest(BaseModel):
    """Represent a plugin approval request."""

    manifest_digest: str = Field(min_length=64, max_length=64)


@router.get("", response_model=list[PluginRegistryEntry])
def list_plugins(service: PluginRegistryServiceDep) -> list[PluginRegistryEntry]:
    """List plugin registry entries.

    Args:
        service: Plugin registry service dependency.

    Returns:
        Registered plugin entries.
    """

    return service.list_plugins()


@router.post("", response_model=PluginRegistryEntry)
def register_plugin(
    manifest: PluginManifest,
    service: PluginRegistryServiceDep,
    audit_service: AuditServiceDep,
    principal: ManagePluginsPrincipalDep,
) -> PluginRegistryEntry:
    """Validate and register a plugin manifest.

    Args:
        manifest: Plugin manifest.
        service: Plugin registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Registered plugin entry.

    Raises:
        HTTPException: If sandbox validation fails.
    """

    try:
        entry = service.register_plugin(manifest)
        audit_service.record(
            principal=principal,
            action="plugin.register",
            resource_type="plugin",
            resource_id=str(entry.plugin_id),
            metadata={"name": entry.manifest.name, "type": entry.manifest.plugin_type},
        )
        return entry
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/sandbox-tests", response_model=SandboxTestReport)
def run_sandbox_tests(
    manifest: PluginManifest,
    audit_service: AuditServiceDep,
    principal: ManagePluginsPrincipalDep,
) -> SandboxTestReport:
    """Run sandbox policy tests for a plugin manifest.

    Args:
        manifest: Plugin manifest.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Sandbox test execution report.
    """

    report = run_plugin_sandbox_tests(manifest)
    audit_service.record(
        principal=principal,
        action="plugin.sandbox_tests.run",
        resource_type="plugin_manifest",
        resource_id=manifest.name,
        metadata={
            "plugin_type": manifest.plugin_type,
            "passed": report.passed,
            "test_count": len(report.results),
        },
    )
    return report


@router.get("/{plugin_id}", response_model=PluginRegistryEntry)
def get_plugin(
    plugin_id: UUID,
    service: PluginRegistryServiceDep,
) -> PluginRegistryEntry:
    """Get one plugin registry entry.

    Args:
        plugin_id: Plugin identifier.
        service: Plugin registry service dependency.

    Returns:
        Plugin registry entry.

    Raises:
        HTTPException: If no plugin exists for the ID.
    """

    try:
        return service.get_plugin(plugin_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Plugin not found.") from error


@router.post("/{plugin_id}/approve", response_model=PluginRegistryEntry)
def approve_plugin(
    plugin_id: UUID,
    request: PluginApprovalRequest,
    service: PluginRegistryServiceDep,
    audit_service: AuditServiceDep,
    principal: ManagePluginsPrincipalDep,
) -> PluginRegistryEntry:
    """Approve and enable one plugin registry entry.

    Args:
        plugin_id: Plugin identifier.
        request: Plugin approval request payload.
        service: Plugin registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Enabled plugin registry entry.

    Raises:
        HTTPException: If no plugin exists or approval validation fails.
    """

    try:
        entry = service.approve_plugin(
            plugin_id,
            request.manifest_digest,
            principal.user_id,
        )
        audit_service.record(
            principal=principal,
            action="plugin.approve",
            resource_type="plugin",
            resource_id=str(plugin_id),
            metadata={
                "status": entry.status,
                "manifest_digest": entry.manifest_digest,
            },
        )
        return entry
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Plugin not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{plugin_id}/status", response_model=PluginRegistryEntry)
def update_plugin_status(
    plugin_id: UUID,
    request: PluginStatusUpdateRequest,
    service: PluginRegistryServiceDep,
    audit_service: AuditServiceDep,
    principal: ManagePluginsPrincipalDep,
) -> PluginRegistryEntry:
    """Update one plugin registry status.

    Args:
        plugin_id: Plugin identifier.
        request: Status update payload.
        service: Plugin registry service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Updated plugin registry entry.

    Raises:
        HTTPException: If no plugin exists or status validation fails.
    """

    try:
        entry = service.update_status(plugin_id, request.status)
        audit_service.record(
            principal=principal,
            action="plugin.status.update",
            resource_type="plugin",
            resource_id=str(plugin_id),
            metadata={"status": entry.status},
        )
        return entry
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Plugin not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
