"""SQLAlchemy ORM models for simulation persistence."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Provide shared SQLAlchemy declarative metadata."""


class AccountRecord(Base):
    """Persist a simulated account that is never linked to a real exchange."""

    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    initial_equity: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    total_equity: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)


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
    speed_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
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
    open: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    high: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    low: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    close: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    volume: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    quote_volume: Mapped[Decimal | None] = mapped_column(
        Numeric(38, 18, asdecimal=True)
    )
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


class DecisionRecord(Base):
    """Persist a structured trade intent emitted by an agent."""

    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    target_notional: Mapped[Decimal | None] = mapped_column(
        Numeric(38, 18, asdecimal=True)
    )
    max_leverage: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
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
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    approved_target_weight: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    max_order_notional: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    triggered_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_sim_time: Mapped[datetime] = mapped_column(
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
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18, asdecimal=True))
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
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    fee: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    slippage_bps: Mapped[Decimal] = mapped_column(
        Numeric(38, 18, asdecimal=True), nullable=False
    )
    filled_at_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
