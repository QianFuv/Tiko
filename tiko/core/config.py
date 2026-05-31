"""Application settings for the Tiko simulation platform."""

from decimal import Decimal
from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define runtime settings for API, simulation, and data safety defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TIKO_",
        extra="ignore",
    )

    app_name: str = "Tiko"
    api_prefix: str = "/api"
    environment: str = "local"
    safety_mode: str = "simulation_only"
    allow_private_exchange_methods: bool = False
    allow_trading_credentials: bool = False
    database_url: str | None = None
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TIKO_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
        ),
    )
    openrouter_model: str = Field(
        default="openrouter/free",
        min_length=1,
        validation_alias=AliasChoices("TIKO_OPENROUTER_MODEL", "OPENROUTER_MODEL"),
    )
    openrouter_chat_endpoint: str = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        min_length=1,
        validation_alias=AliasChoices(
            "TIKO_OPENROUTER_CHAT_ENDPOINT", "OPENROUTER_CHAT_ENDPOINT"
        ),
    )
    openrouter_timeout_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "TIKO_OPENROUTER_TIMEOUT_SECONDS", "OPENROUTER_TIMEOUT_SECONDS"
        ),
    )
    default_base_currency: str = "USDT"
    default_initial_equity: int = Field(default=100_000, ge=1)
    minimum_trade_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    minimum_data_quality_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_target_weight: Decimal = Field(
        default=Decimal("0.25"), ge=Decimal("0"), le=Decimal("1")
    )
    max_order_notional: Decimal = Field(default=Decimal("25000"), ge=Decimal("0"))
    synthetic_seed: int = 42


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings loaded from environment variables.

    Returns:
        Application settings with architecture-safe defaults.
    """

    return Settings()
