"""Market data policy and symbol routes."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tiko.api.dependencies import (
    get_audit_service,
    get_simulation_service,
    require_permission,
)
from tiko.domain.market import Candle, MarketEvent, OrderBookSnapshot
from tiko.domain.security import Principal
from tiko.services import AuditService, SimulationService

router = APIRouter(prefix="/market", tags=["market"])
SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ManageSimulationPrincipalDep = Annotated[
    Principal, Depends(require_permission("manage_simulations"))
]


class MarketSymbolsResponse(BaseModel):
    """Represent symbols available to the simulated environment."""

    symbols: list[str]
    data_policy: str
    private_methods_allowed: bool


class MarketOrderBookResponse(BaseModel):
    """Represent read-only order book availability for a symbol."""

    symbol: str
    run_id: UUID | None = None
    as_of: datetime | None = None
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    mid_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    spread_bps: Decimal | None = Field(default=None, ge=Decimal("0"))
    depth_1pct_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    source: str | None = None
    data_policy: str
    private_methods_allowed: bool


class MarketEventInjectRequest(BaseModel):
    """Represent a controlled market event injection request."""

    run_id: UUID
    type: Literal[
        "candle_closed",
        "tick",
        "orderbook_snapshot",
        "funding_update",
        "news_event",
        "liquidity_shock",
        "volatility_shock",
        "system_event",
    ]
    symbol: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    source: str = Field(default="manual", min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    simulated_time: datetime | None = None


@router.get("/symbols", response_model=MarketSymbolsResponse)
def list_market_symbols(service: SimulationServiceDep) -> MarketSymbolsResponse:
    """Return symbols known from runs or default demo symbols.

    Args:
        service: Simulation service dependency.

    Returns:
        Market symbols and read-only policy.
    """

    symbols = sorted({symbol for run in service.list_runs() for symbol in run.symbols})
    return MarketSymbolsResponse(
        symbols=symbols or ["BTCUSDT", "ETHUSDT"],
        data_policy="read_only_public_market_data",
        private_methods_allowed=False,
    )


@router.get("/candles", response_model=list[Candle])
def list_market_candles(
    service: SimulationServiceDep,
    run_id: Annotated[UUID, Query()],
) -> list[Candle]:
    """List candles observed by one simulation run.

    Args:
        service: Simulation service dependency.
        run_id: Simulation run identifier.

    Returns:
        Run candles.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        return service.list_candles(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error


@router.get("/orderbook", response_model=MarketOrderBookResponse)
def get_market_orderbook(
    service: SimulationServiceDep,
    symbol: Annotated[str, Query(min_length=1)],
    run_id: Annotated[UUID | None, Query()] = None,
) -> MarketOrderBookResponse:
    """Return the latest read-only order book snapshot for a symbol.

    Args:
        service: Simulation service dependency.
        symbol: Market symbol.
        run_id: Optional simulation run identifier.

    Returns:
        Latest order book snapshot or an explicit unavailable response.

    Raises:
        HTTPException: If the supplied run does not exist.
    """

    try:
        snapshot = service.get_latest_orderbook_snapshot(symbol=symbol, run_id=run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    if snapshot is not None:
        return build_orderbook_response(snapshot, run_id)
    return MarketOrderBookResponse(
        symbol=symbol,
        run_id=run_id,
        bids=[],
        asks=[],
        data_policy="read_only_orderbook_snapshot_unavailable",
        private_methods_allowed=False,
    )


def build_orderbook_response(
    snapshot: OrderBookSnapshot, run_id: UUID | None
) -> MarketOrderBookResponse:
    """Build an API response from a read-only order book snapshot.

    Args:
        snapshot: Source order book snapshot.
        run_id: Optional scoped run identifier from the request.

    Returns:
        API response with snapshot metadata and safety policy.
    """

    return MarketOrderBookResponse(
        symbol=snapshot.symbol,
        run_id=run_id,
        as_of=snapshot.as_of,
        bids=snapshot.bids,
        asks=snapshot.asks,
        mid_price=snapshot.mid_price,
        spread_bps=snapshot.spread_bps,
        depth_1pct_usd=snapshot.depth_1pct_usd,
        source=snapshot.source,
        data_policy="read_only_simulated_orderbook_snapshot",
        private_methods_allowed=False,
    )


@router.get("/events", response_model=list[MarketEvent])
def list_market_events(service: SimulationServiceDep) -> list[MarketEvent]:
    """List market events across simulation runs.

    Args:
        service: Simulation service dependency.

    Returns:
        Market events across runs.
    """

    return service.list_all_events()


@router.post("/events/inject", response_model=MarketEvent)
def inject_market_event(
    request: MarketEventInjectRequest,
    service: SimulationServiceDep,
    audit_service: AuditServiceDep,
    principal: ManageSimulationPrincipalDep,
) -> MarketEvent:
    """Inject a controlled market event into a simulation run.

    Args:
        request: Market event injection request.
        service: Simulation service dependency.
        audit_service: Audit service dependency.
        principal: Authorized caller principal.

    Returns:
        Injected market event.

    Raises:
        HTTPException: If the run does not exist.
    """

    try:
        event = service.inject_market_event(
            run_id=request.run_id,
            type_=request.type,
            symbol=request.symbol,
            payload=request.payload,
            source=request.source,
            confidence=request.confidence,
            simulated_time=request.simulated_time,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Simulation run not found."
        ) from error
    audit_service.record(
        principal=principal,
        action="market.event.inject",
        resource_type="market_event",
        resource_id=str(event.event_id),
        metadata={"run_id": str(request.run_id), "type": event.type},
    )
    return event
