"""Run benchmark and comparison schemas."""

from decimal import Decimal
from uuid import UUID

from tiko.domain.base import DomainModel


class RunBenchmark(DomainModel):
    """Represent reproducible summary metrics for one run."""

    run_id: UUID
    fingerprint: str
    total_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_drawdown: Decimal
    decision_count: int
    order_count: int
    fill_count: int


class RunComparison(DomainModel):
    """Represent a pairwise comparison between two simulation runs."""

    baseline: RunBenchmark
    candidate: RunBenchmark
    fingerprints_match: bool
    deltas: dict[str, Decimal | int]
