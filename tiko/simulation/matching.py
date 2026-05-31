"""Matching engine for internal simulated orders."""

from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from tiko.domain.order import Fill, OrderRequest, SimOrder
from tiko.simulation.fee import FeeEngine
from tiko.simulation.slippage import SlippageContext, SlippageEngine

TimeInForce = Literal["gtc", "ioc", "fok"]
SUPPORTED_TIME_IN_FORCE: frozenset[TimeInForce] = frozenset(("gtc", "ioc", "fok"))


class MatchingEngine:
    """Create simulated immediate fills for internal market orders."""

    def __init__(
        self,
        fee_engine: FeeEngine | None = None,
        slippage_engine: SlippageEngine | None = None,
        maker_fee_engine: FeeEngine | None = None,
    ) -> None:
        """Initialize matching dependencies.

        Args:
            fee_engine: Optional taker fee engine.
            slippage_engine: Optional slippage engine.
            maker_fee_engine: Optional maker fee engine for limit fills.
        """

        self._taker_fee_engine = fee_engine or FeeEngine()
        self._slippage_engine = slippage_engine or SlippageEngine()
        self._maker_fee_engine = maker_fee_engine or self._taker_fee_engine

    def match_market_order(
        self,
        order_request: OrderRequest,
        reference_price: Decimal,
        slippage_context: SlippageContext | None = None,
    ) -> tuple[SimOrder, Fill]:
        """Match an internal market order request immediately.

        Args:
            order_request: Internal order request.
            reference_price: Current market reference price.
            slippage_context: Optional market context for effective slippage.

        Returns:
            Filled simulated order and fill.

        Raises:
            ValueError: If the request is not a market order.
        """

        if order_request.order_type != "market":
            raise ValueError("MatchingEngine currently supports market orders only.")
        slippage_bps = self._slippage_engine.calculate_market_slippage_bps(
            slippage_context
        )
        fill_price = self._slippage_engine.apply_market_slippage_bps(
            reference_price, order_request.side, slippage_bps
        )
        fee = self._taker_fee_engine.calculate_fee(order_request.quantity, fill_price)
        order_id = uuid4()
        order = self._build_order(order_request, order_id, "filled")
        fill = Fill(
            fill_id=uuid4(),
            order_id=order_id,
            run_id=order_request.run_id,
            symbol=order_request.symbol,
            side=order_request.side,
            quantity=order_request.quantity,
            price=fill_price,
            fee=fee,
            slippage_bps=slippage_bps,
            filled_at_sim_time=order_request.submitted_at_sim_time,
        )
        return order, fill

    def match_limit_order(
        self,
        order_request: OrderRequest,
        reference_price: Decimal,
        available_quantity: Decimal | None = None,
        time_in_force: TimeInForce = "gtc",
    ) -> tuple[SimOrder, Fill | None]:
        """Match an internal limit order request against a reference price.

        Args:
            order_request: Internal limit order request.
            reference_price: Current market reference price.
            available_quantity: Optional simulated depth available to fill.
            time_in_force: Limit order expiry behavior.

        Returns:
            Simulated order and optional fill.

        Raises:
            ValueError: If the request is invalid.
        """

        if order_request.order_type != "limit":
            raise ValueError("Limit matching requires a limit order request.")
        if time_in_force not in SUPPORTED_TIME_IN_FORCE:
            raise ValueError("Unsupported time_in_force.")
        if order_request.limit_price is None:
            raise ValueError("Limit order requests require limit_price.")
        if available_quantity is not None and available_quantity < Decimal("0"):
            raise ValueError("available_quantity must not be negative.")
        order_id = uuid4()
        if not self._limit_crosses(
            order_request.side, order_request.limit_price, reference_price
        ):
            unfilled_status = self._unfilled_limit_status(time_in_force)
            return self._build_order(order_request, order_id, unfilled_status), None
        fill_quantity = self._limit_fill_quantity(order_request, available_quantity)
        if fill_quantity <= Decimal("0"):
            unfilled_status = self._unfilled_limit_status(time_in_force)
            return self._build_order(order_request, order_id, unfilled_status), None
        if time_in_force == "fok" and fill_quantity < order_request.quantity:
            return self._build_order(order_request, order_id, "expired"), None
        status: Literal["partially_filled", "filled"] = (
            "filled" if fill_quantity == order_request.quantity else "partially_filled"
        )
        order = self._build_order(order_request, order_id, status)
        fill = Fill(
            fill_id=uuid4(),
            order_id=order_id,
            run_id=order_request.run_id,
            symbol=order_request.symbol,
            side=order_request.side,
            quantity=fill_quantity,
            price=reference_price,
            fee=self._maker_fee_engine.calculate_fee(fill_quantity, reference_price),
            slippage_bps=Decimal("0"),
            filled_at_sim_time=order_request.submitted_at_sim_time,
        )
        return order, fill

    def _build_order(
        self,
        order_request: OrderRequest,
        order_id: UUID,
        status: Literal["open", "partially_filled", "filled", "expired"],
    ) -> SimOrder:
        """Build a simulated order from one request.

        Args:
            order_request: Source order request.
            order_id: Generated order identifier.
            status: Simulated order status.

        Returns:
            Simulated order record.
        """

        return SimOrder(
            order_id=order_id,
            run_id=order_request.run_id,
            account_id=order_request.account_id,
            decision_id=order_request.decision_id,
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            limit_price=order_request.limit_price,
            status=status,
            submitted_at_sim_time=order_request.submitted_at_sim_time,
            updated_at_sim_time=order_request.submitted_at_sim_time,
        )

    def _limit_fill_quantity(
        self,
        order_request: OrderRequest,
        available_quantity: Decimal | None,
    ) -> Decimal:
        """Calculate filled quantity for a crossed limit order.

        Args:
            order_request: Source order request.
            available_quantity: Optional simulated depth available to fill.

        Returns:
            Filled quantity.
        """

        if available_quantity is None:
            return order_request.quantity
        return min(order_request.quantity, available_quantity)

    def _unfilled_limit_status(
        self,
        time_in_force: TimeInForce,
    ) -> Literal["open", "expired"]:
        """Return the order status for an unfilled limit order.

        Args:
            time_in_force: Limit order expiry behavior.

        Returns:
            Open for GTC orders and expired for immediate expiry policies.
        """

        if time_in_force == "gtc":
            return "open"
        return "expired"

    def _limit_crosses(
        self,
        side: str,
        limit_price: Decimal,
        reference_price: Decimal,
    ) -> bool:
        """Return whether a limit order crosses the current reference price.

        Args:
            side: Order side.
            limit_price: Order limit price.
            reference_price: Current market reference price.

        Returns:
            Whether the limit order can fill immediately.
        """

        if side == "buy":
            return reference_price <= limit_price
        return reference_price >= limit_price
