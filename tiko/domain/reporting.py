"""Reporting and alerting schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

ReportType = Literal["simulation", "decision", "experiment"]
ReportFormat = Literal["markdown"]
AlertCategory = Literal[
    "pnl",
    "drawdown",
    "agent_timeout",
    "data_quality",
    "order_anomaly",
    "runtime_stuck",
    "worker_health",
    "risk_circuit_breaker",
    "model_degradation",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "acknowledged", "resolved"]


class ReportArtifact(DomainModel):
    """Represent a structured report artifact."""

    report_id: UUID
    run_id: UUID
    report_type: ReportType
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    sections: dict[str, object]
    created_at_sim_time: datetime
    created_at: datetime


class RenderedReport(DomainModel):
    """Represent a rendered human-readable report document."""

    report_id: UUID
    report_type: ReportType
    format: ReportFormat
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    rendered_at: datetime


class Alert(DomainModel):
    """Represent an operator-facing simulation alert."""

    alert_id: UUID
    run_id: UUID
    category: AlertCategory
    severity: AlertSeverity
    message: str = Field(min_length=1)
    status: AlertStatus
    created_at_sim_time: datetime
    created_at: datetime
