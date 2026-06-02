"""create baseline schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import tiko.db.models

revision: str = "a749f2347963"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_currency", sa.String(length=16), nullable=False),
        sa.Column("initial_equity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("cash_balance", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("total_equity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("realized_pnl", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("unrealized_pnl", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("max_drawdown", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_table(
        "assets",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("base_asset", sa.String(length=32), nullable=False),
        sa.Column("quote_asset", sa.String(length=32), nullable=False),
        sa.Column("market_type", sa.String(length=32), nullable=False),
        sa.Column("tick_size", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("lot_size", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("min_notional", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("fee_tier", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("timeframes", sa.JSON(), nullable=False),
        sa.Column("candle_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
    )
    op.create_table(
        "model_registry",
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("model_type", sa.String(length=32), nullable=False),
        sa.Column("algorithm", sa.String(length=128), nullable=False),
        sa.Column("training_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("validation_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("model_id"),
    )
    op.create_table(
        "plugin_registry",
        sa.Column("plugin_id", sa.String(length=36), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_digest", sa.String(length=64), nullable=False),
        sa.Column("sandbox_result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("plugin_id"),
    )
    op.create_table(
        "reports",
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "dataset_candles",
        sa.Column("candle_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=32), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("high", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("low", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("close", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("volume", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("quote_volume", tiko.db.models.ExactDecimal(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
        ),
        sa.PrimaryKeyConstraint("candle_id"),
    )
    op.create_table(
        "raw_market_data_records",
        sa.Column("raw_record_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
        ),
        sa.PrimaryKeyConstraint("raw_record_id"),
    )
    op.create_table(
        "dataset_quality_reports",
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("has_errors", sa.Boolean(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
        ),
        sa.PrimaryKeyConstraint("dataset_id"),
    )
    op.create_table(
        "experiments",
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=36), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
        ),
        sa.PrimaryKeyConstraint("experiment_id"),
    )
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "simulation_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("start_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_sim_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("speed_multiplier", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_table(
        "candles",
        sa.Column("candle_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=32), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("high", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("low", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("close", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("volume", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("quote_volume", tiko.db.models.ExactDecimal(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("candle_id"),
    )
    op.create_table(
        "decisions",
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("input_data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("market_type", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_weight", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("target_notional", tiko.db.models.ExactDecimal(), nullable=True),
        sa.Column("max_leverage", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expected_holding_period", sa.String(length=64), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("invalidation_conditions", sa.JSON(), nullable=False),
        sa.Column("data_quality_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_table(
        "feature_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_table(
        "market_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("simulated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "realtime_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("simulated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "metric_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("simulated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_table(
        "observation_snapshots",
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_table(
        "orderbook_snapshots",
        sa.Column("snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bids", sa.JSON(), nullable=False),
        sa.Column("asks", sa.JSON(), nullable=False),
        sa.Column("mid_price", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("spread_bps", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("depth_1pct_usd", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(length=255), nullable=True),
        sa.Column("expected_checksum", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("simulated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash_balance", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("total_equity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("realized_pnl", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("unrealized_pnl", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("max_drawdown", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("gross_exposure", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("net_exposure", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_table(
        "positions",
        sa.Column("position_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("avg_entry_price", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("mark_price", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("notional", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("leverage", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("unrealized_pnl", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("realized_pnl", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("liquidation_price", tiko.db.models.ExactDecimal(), nullable=True),
        sa.Column("updated_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("position_id"),
    )
    op.create_table(
        "simulations",
        sa.Column("simulation_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=64), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
        ),
        sa.PrimaryKeyConstraint("simulation_id"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("agent_run_id"),
    )
    op.create_table(
        "decision_reviews",
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("horizon", sa.String(length=32), nullable=False),
        sa.Column("realized_return", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column(
            "max_adverse_excursion", tiko.db.models.ExactDecimal(), nullable=False
        ),
        sa.Column(
            "max_favorable_excursion", tiko.db.models.ExactDecimal(), nullable=False
        ),
        sa.Column("was_correct_directionally", sa.Boolean(), nullable=False),
        sa.Column("error_tags", sa.JSON(), nullable=False),
        sa.Column("reviewer_summary", sa.Text(), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("review_id"),
    )
    op.create_table(
        "memory_entries",
        sa.Column("memory_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("available_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("memory_id"),
    )
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("limit_price", tiko.db.models.ExactDecimal(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_table(
        "risk_reviews",
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "original_target_weight", tiko.db.models.ExactDecimal(), nullable=False
        ),
        sa.Column(
            "approved_target_weight", tiko.db.models.ExactDecimal(), nullable=False
        ),
        sa.Column("max_order_notional", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("triggered_rules", sa.JSON(), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("review_id"),
    )
    op.create_table(
        "agent_messages",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.agent_run_id"],
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_table(
        "fills",
        sa.Column("fill_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("price", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("fee", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("slippage_bps", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("filled_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("fill_id"),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("ledger_entry_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("fill_id", sa.String(length=36), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("quantity", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("price", tiko.db.models.ExactDecimal(), nullable=True),
        sa.Column("notional", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("cash_delta", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("fee", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("realized_pnl_delta", tiko.db.models.ExactDecimal(), nullable=False),
        sa.Column("created_at_sim_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
        ),
        sa.ForeignKeyConstraint(
            ["fill_id"],
            ["fills.fill_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("ledger_entry_id"),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("ledger_entries")
    op.drop_table("fills")
    op.drop_table("agent_messages")
    op.drop_table("risk_reviews")
    op.drop_table("orders")
    op.drop_table("memory_entries")
    op.drop_table("decision_reviews")
    op.drop_table("agent_runs")
    op.drop_table("simulations")
    op.drop_table("positions")
    op.drop_table("portfolio_snapshots")
    op.drop_table("orderbook_snapshots")
    op.drop_table("observation_snapshots")
    op.drop_table("metric_snapshots")
    op.drop_table("realtime_events")
    op.drop_table("market_events")
    op.drop_table("feature_snapshots")
    op.drop_table("decisions")
    op.drop_table("candles")
    op.drop_table("alerts")
    op.drop_table("simulation_runs")
    op.drop_table("projects")
    op.drop_table("experiments")
    op.drop_table("dataset_quality_reports")
    op.drop_table("raw_market_data_records")
    op.drop_table("dataset_candles")
    op.drop_table("users")
    op.drop_table("reports")
    op.drop_table("plugin_registry")
    op.drop_table("model_registry")
    op.drop_table("datasets")
    op.drop_table("audit_logs")
    op.drop_table("assets")
    op.drop_table("accounts")
