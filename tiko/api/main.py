"""FastAPI application factory for the simulation control plane."""

from fastapi import FastAPI

from tiko.api.routes import (
    agents,
    comparisons,
    decisions,
    health,
    market,
    models,
    orders,
    plugins,
    portfolio,
    reports,
    risk,
    simulations,
    websocket,
)
from tiko.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application.
    """

    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    application.include_router(health.router, prefix=settings.api_prefix)
    application.include_router(market.router, prefix=settings.api_prefix)
    application.include_router(agents.router, prefix=settings.api_prefix)
    application.include_router(comparisons.router, prefix=settings.api_prefix)
    application.include_router(models.router, prefix=settings.api_prefix)
    application.include_router(plugins.router, prefix=settings.api_prefix)
    application.include_router(reports.router, prefix=settings.api_prefix)
    application.include_router(simulations.router, prefix=settings.api_prefix)
    application.include_router(decisions.router, prefix=settings.api_prefix)
    application.include_router(portfolio.router, prefix=settings.api_prefix)
    application.include_router(orders.router, prefix=settings.api_prefix)
    application.include_router(risk.router, prefix=settings.api_prefix)
    application.include_router(websocket.router)
    return application


app = create_app()
