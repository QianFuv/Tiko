"""FastAPI dependency providers for in-memory services."""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException

from tiko.core.auth import has_permission
from tiko.core.config import get_settings
from tiko.domain.security import Permission, Principal, Role
from tiko.services import (
    AuditService,
    ModelRegistryService,
    PluginRegistryService,
    SimulationService,
)


@lru_cache
def get_simulation_service() -> SimulationService:
    """Return the process-local simulation service singleton.

    Returns:
        In-memory simulation service.
    """

    return SimulationService(get_settings())


@lru_cache
def get_model_registry_service() -> ModelRegistryService:
    """Return the process-local model registry service singleton.

    Returns:
        In-memory model registry service.
    """

    return ModelRegistryService()


@lru_cache
def get_plugin_registry_service() -> PluginRegistryService:
    """Return the process-local plugin registry service singleton.

    Returns:
        In-memory plugin registry service.
    """

    return PluginRegistryService()


@lru_cache
def get_audit_service() -> AuditService:
    """Return the process-local audit service singleton.

    Returns:
        In-memory audit service.
    """

    return AuditService()


def get_current_principal(
    role_header: Annotated[str | None, Header(alias="X-Tiko-Role")] = None,
    user_header: Annotated[str | None, Header(alias="X-Tiko-User")] = None,
) -> Principal:
    """Resolve the current caller from request headers.

    Args:
        role_header: Optional role header.
        user_header: Optional user identifier header.

    Returns:
        Current principal.

    Raises:
        HTTPException: If the role header is invalid.
    """

    role = role_header or "viewer"
    if role not in {"admin", "researcher", "operator", "viewer"}:
        raise HTTPException(status_code=401, detail="Invalid Tiko role.")
    return Principal(user_id=user_header or "anonymous", role=cast(Role, role))


def require_permission(
    permission: Permission,
) -> Callable[[Principal], Principal]:
    """Create a dependency that enforces one permission.

    Args:
        permission: Required permission.

    Returns:
        FastAPI dependency callable.
    """

    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        """Validate the caller permission.

        Args:
            principal: Current caller.

        Returns:
            Authorized principal.

        Raises:
            HTTPException: If the caller lacks permission.
        """

        if not has_permission(principal, permission):
            raise HTTPException(status_code=403, detail="Insufficient permission.")
        return principal

    return dependency


def reset_simulation_service() -> None:
    """Clear the cached simulation service for tests."""

    get_simulation_service.cache_clear()
    get_model_registry_service.cache_clear()
    get_plugin_registry_service.cache_clear()
    get_audit_service.cache_clear()
