"""FastAPI dependency providers for in-memory services."""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine

from tiko.core.auth import has_permission
from tiko.core.config import get_settings
from tiko.db import (
    SimulationRepository,
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
from tiko.domain.security import Permission, Principal, Role
from tiko.services import (
    AuditService,
    DatasetService,
    ExperimentService,
    ModelRegistryService,
    PluginRegistryService,
    RuntimeService,
    SimulationService,
)


@lru_cache
def get_database_engine() -> Engine | None:
    """Return the configured database engine when persistence is enabled.

    Returns:
        SQLAlchemy engine or `None` when no database URL is configured.
    """

    settings = get_settings()
    if settings.database_url is None:
        return None
    engine = create_database_engine(settings.database_url)
    create_all_tables(engine)
    return engine


@lru_cache
def get_persistence_repository() -> SimulationRepository | None:
    """Return the shared persistence repository when configured.

    Returns:
        SQLAlchemy repository or `None` for process-local mode.
    """

    engine = get_database_engine()
    if engine is None:
        return None
    return SimulationRepository(create_session_factory(engine))


@lru_cache
def get_simulation_service() -> SimulationService:
    """Return the process-local simulation service singleton.

    Returns:
        Simulation service.
    """

    return SimulationService(get_settings(), repository=get_persistence_repository())


@lru_cache
def get_model_registry_service() -> ModelRegistryService:
    """Return the process-local model registry service singleton.

    Returns:
        Model registry service.
    """

    return ModelRegistryService(repository=get_persistence_repository())


@lru_cache
def get_plugin_registry_service() -> PluginRegistryService:
    """Return the process-local plugin registry service singleton.

    Returns:
        Plugin registry service.
    """

    return PluginRegistryService(repository=get_persistence_repository())


@lru_cache
def get_audit_service() -> AuditService:
    """Return the process-local audit service singleton.

    Returns:
        Audit service.
    """

    return AuditService(repository=get_persistence_repository())


@lru_cache
def get_dataset_service() -> DatasetService:
    """Return the process-local dataset service singleton.

    Returns:
        Dataset service.
    """

    return DatasetService(repository=get_persistence_repository())


@lru_cache
def get_experiment_service() -> ExperimentService:
    """Return the process-local experiment service singleton.

    Returns:
        Experiment service.
    """

    return ExperimentService(repository=get_persistence_repository())


@lru_cache
def get_runtime_service() -> RuntimeService:
    """Return the process-local runtime service singleton.

    Returns:
        In-memory runtime service.
    """

    return RuntimeService()


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

    engine = get_database_engine()
    get_simulation_service.cache_clear()
    get_model_registry_service.cache_clear()
    get_plugin_registry_service.cache_clear()
    get_audit_service.cache_clear()
    get_dataset_service.cache_clear()
    get_experiment_service.cache_clear()
    get_runtime_service.cache_clear()
    get_persistence_repository.cache_clear()
    get_database_engine.cache_clear()
    get_settings.cache_clear()
    if engine is not None:
        engine.dispose()
