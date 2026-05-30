"""Application settings for the Tiko simulation platform."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define runtime settings for API, simulation, and data safety defaults."""

    model_config = SettingsConfigDict(env_prefix="TIKO_", extra="ignore")

    app_name: str = "Tiko"
    api_prefix: str = "/api"
    environment: str = "local"
    safety_mode: str = "simulation_only"
    allow_private_exchange_methods: bool = False
    allow_trading_credentials: bool = False
    default_base_currency: str = "USDT"
    default_initial_equity: int = Field(default=100_000, ge=1)
    minimum_trade_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    synthetic_seed: int = 42


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings loaded from environment variables.

    Returns:
        Application settings with architecture-safe defaults.
    """

    return Settings()
