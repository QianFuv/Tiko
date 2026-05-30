"""FastAPI application factory for the simulation control plane."""

from fastapi import FastAPI

from tiko.api.routes import (
    decisions,
    health,
    market,
    orders,
    portfolio,
    risk,
    simulations,
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
    application.include_router(simulations.router, prefix=settings.api_prefix)
    application.include_router(decisions.router, prefix=settings.api_prefix)
    application.include_router(portfolio.router, prefix=settings.api_prefix)
    application.include_router(orders.router, prefix=settings.api_prefix)
    application.include_router(risk.router, prefix=settings.api_prefix)
    return application


app = create_app()
