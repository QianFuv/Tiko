"""FastAPI dependency providers for in-memory services."""

from functools import lru_cache

from tiko.core.config import get_settings
from tiko.services import SimulationService


@lru_cache
def get_simulation_service() -> SimulationService:
    """Return the process-local simulation service singleton.

    Returns:
        In-memory simulation service.
    """

    return SimulationService(get_settings())


def reset_simulation_service() -> None:
    """Clear the cached simulation service for tests."""

    get_simulation_service.cache_clear()
