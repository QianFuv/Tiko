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
from tiko.domain.market import Candle, MarketEvent
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
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
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
    symbol: Annotated[str, Query(min_length=1)],
) -> MarketOrderBookResponse:
    """Return read-only order book policy metadata for a symbol.

    Args:
        symbol: Market symbol.

    Returns:
        Empty order book placeholder with explicit data policy.
    """

    return MarketOrderBookResponse(
        symbol=symbol,
        bids=[],
        asks=[],
        data_policy="orderbook_storage_not_configured",
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
