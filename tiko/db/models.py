"""SQLAlchemy ORM models for simulation persistence."""

from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, TypeEngine


class ExactDecimal(TypeDecorator[Decimal]):
    """Persist decimals without SQLite floating-point round-trip drift."""

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        """Return a dialect-specific database type for decimal values.

        Args:
            dialect: Active SQLAlchemy database dialect.

        Returns:
            Database type used for the current dialect.
        """

        if dialect.name == "sqlite":
            return cast(TypeEngine[object], dialect.type_descriptor(String(128)))
        return cast(
            TypeEngine[object],
            dialect.type_descriptor(Numeric(38, 18, asdecimal=True)),
        )

    def process_bind_param(
        self, value: Decimal | None, dialect: Dialect
    ) -> str | Decimal | None:
        """Convert a Python decimal before sending it to the database.

        Args:
            value: Decimal value to persist.
            dialect: Active SQLAlchemy database dialect.

        Returns:
            Bound value for the current dialect.
        """

        if value is None:
            return None
        if dialect.name == "sqlite":
            return str(value)
        return value

    def process_result_value(
        self, value: object | None, dialect: Dialect
    ) -> Decimal | None:
        """Convert a database value back to a Python decimal.

        Args:
            value: Raw database value.
            dialect: Active SQLAlchemy database dialect.

        Returns:
            Decimal value or `None`.
        """

        if value is None:
            return None
        return Decimal(str(value))


class Base(DeclarativeBase):
    """Provide shared SQLAlchemy declarative metadata."""


class AuditLogRecord(Base):
    """Persist an audited control-plane action."""

    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AssetRecord(Base):
    """Persist market instrument reference metadata."""

    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_asset: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_asset: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    lot_size: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    min_notional: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    fee_tier: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False)


class AccountRecord(Base):
    """Persist a simulated account that is never linked to a real exchange."""

    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    initial_equity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    total_equity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    max_drawdown: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class PositionRecord(Base):
    """Persist the current simulated position for an account and symbol."""

    __tablename__ = "positions"

    position_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    mark_price: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    notional: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    leverage: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    liquidation_price: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    updated_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SimulationRunRecord(Base):
    """Persist the lifecycle and current clock state of a simulation run."""

    __tablename__ = "simulation_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.account_id"), nullable=False
    )
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    start_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_sim_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    speed_multiplier: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DatasetMetadataRecord(Base):
    """Persist imported dataset metadata for research workflows."""

    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    candle_count: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DatasetQualityReportRecord(Base):
    """Persist the latest validation report for an imported dataset."""

    __tablename__ = "dataset_quality_reports"

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.dataset_id"), primary_key=True
    )
    total_records: Mapped[int] = mapped_column(nullable=False)
    error_count: Mapped[int] = mapped_column(nullable=False)
    warning_count: Mapped[int] = mapped_column(nullable=False)
    has_errors: Mapped[bool] = mapped_column(nullable=False)
    issues: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class DatasetCandleRecord(Base):
    """Persist normalized candles owned by an imported dataset."""

    __tablename__ = "dataset_candles"

    candle_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    open: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    high: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    low: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    close: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    volume: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    quote_volume: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CandleRecord(Base):
    """Persist a point-in-time candle emitted by a simulation run."""

    __tablename__ = "candles"

    candle_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    open: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    high: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    low: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    close: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    volume: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    quote_volume: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MarketEventRecord(Base):
    """Persist a market or synthetic event generated during a simulation."""

    __tablename__ = "market_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32))
    simulated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class ObservationSnapshotRecord(Base):
    """Persist a point-in-time observation snapshot."""

    __tablename__ = "observation_snapshots"

    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class OrderBookSnapshotRecord(Base):
    """Persist a synthetic or read-only order book snapshot."""

    __tablename__ = "orderbook_snapshots"

    snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bids: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False)
    asks: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False)
    mid_price: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    spread_bps: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    depth_1pct_usd: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)


class FeatureSnapshotRecord(Base):
    """Persist derived point-in-time market features."""

    __tablename__ = "feature_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    features: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)


class AgentRunRecord(Base):
    """Persist an agent evaluation associated with a decision."""

    __tablename__ = "agent_runs"

    agent_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.decision_id"))
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AgentMessageRecord(Base):
    """Persist a structured message in an agent trace."""

    __tablename__ = "agent_messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.agent_run_id"))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DecisionRecord(Base):
    """Persist a structured trade intent emitted by an agent."""

    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    target_notional: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    max_leverage: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    expected_holding_period: Mapped[str] = mapped_column(String(64), nullable=False)
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    invalidation_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    data_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RiskReviewRecord(Base):
    """Persist the independent risk result for a trade intent."""

    __tablename__ = "risk_reviews"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    original_target_weight: Mapped[Decimal] = mapped_column(
        ExactDecimal(), nullable=False
    )
    approved_target_weight: Mapped[Decimal] = mapped_column(
        ExactDecimal(), nullable=False
    )
    max_order_notional: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    triggered_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DecisionReviewRecord(Base):
    """Persist posterior review metrics for a structured trade intent."""

    __tablename__ = "decision_reviews"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    realized_return: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    max_adverse_excursion: Mapped[Decimal] = mapped_column(
        ExactDecimal(), nullable=False
    )
    max_favorable_excursion: Mapped[Decimal] = mapped_column(
        ExactDecimal(), nullable=False
    )
    was_correct_directionally: Mapped[bool] = mapped_column(nullable=False)
    error_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reviewer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MemoryEntryRecord(Base):
    """Persist auxiliary point-in-time memory for simulation review."""

    __tablename__ = "memory_entries"

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    decision_id: Mapped[str | None] = mapped_column(ForeignKey("decisions.decision_id"))
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    available_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ModelRegistryRecord(Base):
    """Persist research model metadata for simulated use review."""

    __tablename__ = "model_registry"

    model_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(128), nullable=False)
    training_dataset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    validation_dataset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExperimentRegistryRecord(Base):
    """Persist research experiment metadata and lifecycle state."""

    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id"))
    model_id: Mapped[str | None] = mapped_column(String(36))
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PluginRegistryRecord(Base):
    """Persist plugin manifests and sandbox validation results."""

    __tablename__ = "plugin_registry"

    plugin_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    manifest: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    sandbox_result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ReportRecord(Base):
    """Persist a structured report artifact."""

    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AlertRecord(Base):
    """Persist a run-scoped alert."""

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class OrderRecord(Base):
    """Persist an internal simulated order."""

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"))
    decision_id: Mapped[str | None] = mapped_column(ForeignKey("decisions.decision_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class FillRecord(Base):
    """Persist a simulated fill produced by the internal matching engine."""

    __tablename__ = "fills"

    fill_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    price: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    fee: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    slippage_bps: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    filled_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class LedgerEntryRecord(Base):
    """Persist a simulated ledger entry produced by internal fills."""

    __tablename__ = "ledger_entries"

    ledger_entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"))
    fill_id: Mapped[str | None] = mapped_column(ForeignKey("fills.fill_id"))
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32))
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    notional: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    cash_delta: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    fee: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    realized_pnl_delta: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PortfolioSnapshotRecord(Base):
    """Persist point-in-time simulated portfolio state."""

    __tablename__ = "portfolio_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"))
    simulated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cash_balance: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    total_equity: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    max_drawdown: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    gross_exposure: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    net_exposure: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MetricSnapshotRecord(Base):
    """Persist point-in-time simulated metrics."""

    __tablename__ = "metric_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    simulated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
