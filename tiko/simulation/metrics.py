"""Metrics calculation for simulated execution runs."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from tiko.domain.order import Fill, SimOrder
from tiko.domain.simulation import SimulationRun


@dataclass(frozen=True)
class ExecutionMetrics:
    """Summarize simulated execution outcomes for a run."""

    run_id: UUID
    order_count: int
    fill_count: int
    total_fees: Decimal
    traded_notional: Decimal
    realized_return: Decimal


class MetricsEngine:
    """Calculate deterministic metrics from simulated artifacts."""

    def summarize_execution(
        self,
        run: SimulationRun,
        orders: Sequence[SimOrder],
        fills: Sequence[Fill],
    ) -> ExecutionMetrics:
        """Summarize order, fill, fee, notional, and return metrics.

        Args:
            run: Simulation run with current account state.
            orders: Simulated orders for the run.
            fills: Simulated fills for the run.

        Returns:
            Execution metrics summary.
        """

        total_fees = sum((fill.fee for fill in fills), Decimal("0"))
        traded_notional = sum(
            (fill.quantity * fill.price for fill in fills), Decimal("0")
        )
        realized_return = (
            run.account.realized_pnl / run.account.initial_equity
            if run.account.initial_equity > Decimal("0")
            else Decimal("0")
        )
        return ExecutionMetrics(
            run_id=run.run_id,
            order_count=len(orders),
            fill_count=len(fills),
            total_fees=total_fees,
            traded_notional=traded_notional,
            realized_return=realized_return,
        )
