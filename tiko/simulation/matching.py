"""Matching engine for internal simulated orders."""

from decimal import Decimal
from uuid import uuid4

from tiko.domain.order import Fill, OrderRequest, SimOrder
from tiko.simulation.fee import FeeEngine
from tiko.simulation.slippage import SlippageEngine


class MatchingEngine:
    """Create simulated immediate fills for internal market orders."""

    def __init__(
        self,
        fee_engine: FeeEngine | None = None,
        slippage_engine: SlippageEngine | None = None,
    ) -> None:
        """Initialize matching dependencies.

        Args:
            fee_engine: Optional fee engine.
            slippage_engine: Optional slippage engine.
        """

        self._fee_engine = fee_engine or FeeEngine()
        self._slippage_engine = slippage_engine or SlippageEngine()

    def match_market_order(
        self, order_request: OrderRequest, reference_price: Decimal
    ) -> tuple[SimOrder, Fill]:
        """Match an internal market order request immediately.

        Args:
            order_request: Internal order request.
            reference_price: Current market reference price.

        Returns:
            Filled simulated order and fill.

        Raises:
            ValueError: If the request is not a market order.
        """

        if order_request.order_type != "market":
            raise ValueError("MatchingEngine currently supports market orders only.")
        fill_price = self._slippage_engine.apply_market_slippage(
            reference_price, order_request.side
        )
        fee = self._fee_engine.calculate_fee(order_request.quantity, fill_price)
        order_id = uuid4()
        order = SimOrder(
            order_id=order_id,
            run_id=order_request.run_id,
            account_id=order_request.account_id,
            decision_id=order_request.decision_id,
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            limit_price=order_request.limit_price,
            status="filled",
            submitted_at_sim_time=order_request.submitted_at_sim_time,
            updated_at_sim_time=order_request.submitted_at_sim_time,
        )
        fill = Fill(
            fill_id=uuid4(),
            order_id=order_id,
            run_id=order_request.run_id,
            symbol=order_request.symbol,
            side=order_request.side,
            quantity=order_request.quantity,
            price=fill_price,
            fee=fee,
            slippage_bps=self._slippage_engine.slippage_bps,
            filled_at_sim_time=order_request.submitted_at_sim_time,
        )
        return order, fill
