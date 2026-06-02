"""Application services for simulation orchestration."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tiko.services.artifacts import ModelArtifactStore, ReportArtifactStore
    from tiko.services.audit import AuditService
    from tiko.services.datasets import DatasetService, DatasetServiceError
    from tiko.services.experiments import ExperimentService
    from tiko.services.models import ModelRegistryService
    from tiko.services.plugins import PluginRegistryService
    from tiko.services.portfolio import PortfolioService
    from tiko.services.realtime import (
        RealtimeFanoutReceipt,
        RealtimeFanoutService,
        RealtimeFanoutSubscriberService,
        RealtimeFanoutSubscription,
    )
    from tiko.services.reports import ReportRenderService
    from tiko.services.risk import RiskService
    from tiko.services.runtime import RuntimeService
    from tiko.services.simulation import SimulationService

EXPORT_MAP: dict[str, tuple[str, str]] = {
    "AuditService": ("tiko.services.audit", "AuditService"),
    "DatasetService": ("tiko.services.datasets", "DatasetService"),
    "DatasetServiceError": ("tiko.services.datasets", "DatasetServiceError"),
    "ExperimentService": ("tiko.services.experiments", "ExperimentService"),
    "ModelRegistryService": ("tiko.services.models", "ModelRegistryService"),
    "ModelArtifactStore": ("tiko.services.artifacts", "ModelArtifactStore"),
    "PortfolioService": ("tiko.services.portfolio", "PortfolioService"),
    "PluginRegistryService": ("tiko.services.plugins", "PluginRegistryService"),
    "ReportArtifactStore": ("tiko.services.artifacts", "ReportArtifactStore"),
    "RealtimeFanoutReceipt": ("tiko.services.realtime", "RealtimeFanoutReceipt"),
    "RealtimeFanoutService": ("tiko.services.realtime", "RealtimeFanoutService"),
    "RealtimeFanoutSubscriberService": (
        "tiko.services.realtime",
        "RealtimeFanoutSubscriberService",
    ),
    "RealtimeFanoutSubscription": (
        "tiko.services.realtime",
        "RealtimeFanoutSubscription",
    ),
    "ReportRenderService": ("tiko.services.reports", "ReportRenderService"),
    "RiskService": ("tiko.services.risk", "RiskService"),
    "RuntimeService": ("tiko.services.runtime", "RuntimeService"),
    "SimulationService": ("tiko.services.simulation", "SimulationService"),
}

__all__ = [
    "AuditService",
    "DatasetService",
    "DatasetServiceError",
    "ExperimentService",
    "ModelRegistryService",
    "ModelArtifactStore",
    "PortfolioService",
    "PluginRegistryService",
    "ReportArtifactStore",
    "RealtimeFanoutReceipt",
    "RealtimeFanoutService",
    "RealtimeFanoutSubscriberService",
    "RealtimeFanoutSubscription",
    "ReportRenderService",
    "RiskService",
    "RuntimeService",
    "SimulationService",
]


def __getattr__(name: str) -> Any:
    """Resolve service exports without eager service module imports.

    Args:
        name: Exported attribute name.

    Returns:
        Exported service object from the owning module.

    Raises:
        AttributeError: If the name is not part of this package's public API.
    """

    try:
        module_name, export_name = EXPORT_MAP[name]
    except KeyError as error:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from error
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value
