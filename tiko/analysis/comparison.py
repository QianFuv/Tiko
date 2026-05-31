"""Deterministic run fingerprint and comparison helpers."""

import hashlib
import json

from tiko.domain.comparison import RunBenchmark, RunComparison
from tiko.domain.decision import TradeIntent
from tiko.domain.order import Fill, SimOrder
from tiko.domain.simulation import SimulationRun


def build_run_fingerprint(
    run: SimulationRun,
    decisions: list[TradeIntent],
    orders: list[SimOrder],
    fills: list[Fill],
) -> str:
    """Build a stable fingerprint over deterministic run artifacts.

    Args:
        run: Simulation run.
        decisions: Run decisions.
        orders: Run orders.
        fills: Run fills.

    Returns:
        SHA-256 fingerprint.
    """

    payload = {
        "account": {
            "total_equity": str(run.account.total_equity),
            "realized_pnl": str(run.account.realized_pnl),
            "unrealized_pnl": str(run.account.unrealized_pnl),
            "max_drawdown": str(run.account.max_drawdown),
        },
        "decisions": [
            {
                "symbol": decision.symbol,
                "action": decision.action,
                "target_weight": str(decision.target_weight),
                "confidence": decision.confidence,
                "created_at_sim_time": decision.created_at_sim_time.isoformat(),
            }
            for decision in decisions
        ],
        "orders": [
            {
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "quantity": str(order.quantity),
                "status": order.status,
                "submitted_at_sim_time": order.submitted_at_sim_time.isoformat(),
            }
            for order in orders
        ],
        "fills": [
            {
                "symbol": fill.symbol,
                "side": fill.side,
                "quantity": str(fill.quantity),
                "price": str(fill.price),
                "fee": str(fill.fee),
                "slippage_bps": str(fill.slippage_bps),
                "filled_at_sim_time": fill.filled_at_sim_time.isoformat(),
            }
            for fill in fills
        ],
    }
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded_payload.encode("utf-8")).hexdigest()


def build_run_benchmark(
    run: SimulationRun,
    decisions: list[TradeIntent],
    orders: list[SimOrder],
    fills: list[Fill],
) -> RunBenchmark:
    """Build benchmark metrics for one run.

    Args:
        run: Simulation run.
        decisions: Run decisions.
        orders: Run orders.
        fills: Run fills.

    Returns:
        Run benchmark summary.
    """

    return RunBenchmark(
        run_id=run.run_id,
        fingerprint=build_run_fingerprint(run, decisions, orders, fills),
        total_equity=run.account.total_equity,
        realized_pnl=run.account.realized_pnl,
        unrealized_pnl=run.account.unrealized_pnl,
        max_drawdown=run.account.max_drawdown,
        decision_count=len(decisions),
        order_count=len(orders),
        fill_count=len(fills),
    )


def compare_run_benchmarks(
    baseline: RunBenchmark,
    candidate: RunBenchmark,
) -> RunComparison:
    """Compare two run benchmarks.

    Args:
        baseline: Baseline run benchmark.
        candidate: Candidate run benchmark.

    Returns:
        Pairwise run comparison.
    """

    return RunComparison(
        baseline=baseline,
        candidate=candidate,
        fingerprints_match=baseline.fingerprint == candidate.fingerprint,
        deltas={
            "total_equity": candidate.total_equity - baseline.total_equity,
            "realized_pnl": candidate.realized_pnl - baseline.realized_pnl,
            "unrealized_pnl": candidate.unrealized_pnl - baseline.unrealized_pnl,
            "max_drawdown": candidate.max_drawdown - baseline.max_drawdown,
            "decision_count": candidate.decision_count - baseline.decision_count,
            "order_count": candidate.order_count - baseline.order_count,
            "fill_count": candidate.fill_count - baseline.fill_count,
        },
    )
