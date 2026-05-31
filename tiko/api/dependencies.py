"""FastAPI dependency providers for in-memory services."""

from functools import lru_cache

from tiko.core.config import get_settings
from tiko.services import ModelRegistryService, PluginRegistryService, SimulationService


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


def reset_simulation_service() -> None:
    """Clear the cached simulation service for tests."""

    get_simulation_service.cache_clear()
    get_model_registry_service.cache_clear()
    get_plugin_registry_service.cache_clear()
