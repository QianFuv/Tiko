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
    redis_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TIKO_REDIS_URL", "REDIS_URL"),
    )
    object_store_endpoint: str | None = None
    primary_historical_connector: str = Field(
        default="ccxt",
        min_length=1,
        validation_alias=AliasChoices(
            "TIKO_PRIMARY_HISTORICAL_CONNECTOR", "PRIMARY_HISTORICAL_CONNECTOR"
        ),
    )
    primary_realtime_connector: str = Field(
        default="cryptofeed",
        min_length=1,
        validation_alias=AliasChoices(
            "TIKO_PRIMARY_REALTIME_CONNECTOR", "PRIMARY_REALTIME_CONNECTOR"
        ),
    )
    raw_storage_uri: str = Field(
        default="file://.tiko/raw",
        min_length=1,
        validation_alias=AliasChoices("TIKO_RAW_STORAGE_URI", "RAW_STORAGE_URI"),
    )
    normalized_storage: str = Field(
        default="postgresql",
        min_length=1,
        validation_alias=AliasChoices("TIKO_NORMALIZED_STORAGE", "NORMALIZED_STORAGE"),
    )
    ccxt_enabled: bool = True
    ccxt_enabled_exchanges: list[str] = Field(
        default=["binance", "okx"],
        validation_alias=AliasChoices(
            "TIKO_CCXT_ENABLED_EXCHANGES", "CCXT_ENABLED_EXCHANGES"
        ),
    )
    ccxt_methods_allowlist: list[str] = Field(
        default=[
            "fetchMarkets",
            "fetchTicker",
            "fetchTickers",
            "fetchTrades",
            "fetchOrderBook",
            "fetchOHLCV",
        ],
        validation_alias=AliasChoices(
            "TIKO_CCXT_METHODS_ALLOWLIST", "CCXT_METHODS_ALLOWLIST"
        ),
    )
    ccxt_methods_blocklist: list[str] = Field(
        default=[
            "createOrder",
            "cancelOrder",
            "cancelAllOrders",
            "editOrder",
            "fetchBalance",
            "fetchOrder",
            "fetchOpenOrders",
            "fetchClosedOrders",
            "fetchMyTrades",
            "fetchPosition",
            "fetchPositions",
            "fetchLedger",
            "withdraw",
            "transfer",
        ],
        validation_alias=AliasChoices(
            "TIKO_CCXT_METHODS_BLOCKLIST", "CCXT_METHODS_BLOCKLIST"
        ),
    )
    cryptofeed_enabled: bool = True
    cryptofeed_channels: list[str] = Field(
        default=["trades", "l2_book", "ticker", "candles", "funding", "open_interest"],
        validation_alias=AliasChoices(
            "TIKO_CRYPTOFEED_CHANNELS", "CRYPTOFEED_CHANNELS"
        ),
    )
    cryptofeed_authenticated_channels_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "TIKO_CRYPTOFEED_AUTHENTICATED_CHANNELS_ENABLED",
            "CRYPTOFEED_AUTHENTICATED_CHANNELS_ENABLED",
        ),
    )
    artifact_root: str = ".tiko/artifacts"
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TIKO_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
        ),
    )
    openrouter_model: str = Field(
        default="liquid/lfm-2.5-1.2b-instruct:free",
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
    openrouter_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices(
            "TIKO_OPENROUTER_TEMPERATURE", "OPENROUTER_TEMPERATURE"
        ),
    )
    openrouter_max_tokens: int = Field(
        default=4096,
        ge=1,
        validation_alias=AliasChoices(
            "TIKO_OPENROUTER_MAX_TOKENS", "OPENROUTER_MAX_TOKENS"
        ),
    )
    agent_coordinator_enabled: bool = True
    agent_market_regime_enabled: bool = True
    agent_technical_enabled: bool = True
    agent_derivatives_enabled: bool = True
    agent_event_enabled: bool = True
    agent_quant_rl_enabled: bool = True
    agent_quant_rl_model_id: str = Field(default="rl_btc_eth_v3", min_length=1)
    agent_critic_enabled: bool = True
    agent_portfolio_enabled: bool = True
    default_base_currency: str = "USDT"
    default_initial_equity: int = Field(default=100_000, ge=1)
    minimum_trade_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    minimum_data_quality_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_target_weight: Decimal = Field(
        default=Decimal("0.25"), ge=Decimal("0"), le=Decimal("1")
    )
    min_order_notional: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    max_order_notional: Decimal = Field(default=Decimal("25000"), ge=Decimal("0"))
    max_leverage: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    max_drawdown: Decimal = Field(default=Decimal("0.20"), ge=Decimal("0"))
    max_daily_loss: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))
    sim_broker_maker_fee_bps: Decimal = Field(default=Decimal("2"), ge=Decimal("0"))
    sim_broker_taker_fee_bps: Decimal = Field(default=Decimal("5"), ge=Decimal("0"))
    sim_broker_slippage_bps: Decimal = Field(default=Decimal("2"), ge=Decimal("0"))
    sim_broker_slippage_volatility_multiplier: Decimal = Field(
        default=Decimal("0.2"), ge=Decimal("0")
    )
    sim_broker_slippage_liquidity_multiplier: Decimal = Field(
        default=Decimal("1.5"), ge=Decimal("0")
    )
    sim_broker_max_market_spread_bps: Decimal = Field(
        default=Decimal("100"), ge=Decimal("0")
    )
    sim_broker_min_market_depth_1pct_usd: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0")
    )
    sim_broker_allow_market: bool = True
    sim_broker_allow_limit: bool = True
    sim_broker_allow_short: bool = True
    sim_broker_allow_leverage: bool = True
    synthetic_funding_rate: Decimal = Decimal("0")
    synthetic_funding_interval_steps: int = Field(default=1, ge=1)
    synthetic_seed: int = 42


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings loaded from environment variables.

    Returns:
        Application settings with architecture-safe defaults.
    """

    return Settings()
