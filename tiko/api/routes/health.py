"""Health and safety status routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from tiko.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Represent API health and safety boundary status."""

    status: str
    safety_mode: str
    private_exchange_methods_allowed: bool
    trading_credentials_allowed: bool


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return API health and architecture safety mode.

    Returns:
        Health status response.
    """

    settings = get_settings()
    return HealthResponse(
        status="healthy",
        safety_mode=settings.safety_mode,
        private_exchange_methods_allowed=settings.allow_private_exchange_methods,
        trading_credentials_allowed=settings.allow_trading_credentials,
    )
