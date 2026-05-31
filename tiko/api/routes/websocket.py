"""WebSocket routes for simulation snapshots."""

from uuid import UUID

from fastapi import APIRouter, WebSocket
from fastapi.encoders import jsonable_encoder

from tiko.api.dependencies import get_simulation_service

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/simulations/{run_id}")
async def simulation_snapshot_websocket(websocket: WebSocket, run_id: UUID) -> None:
    """Send a current event snapshot for a simulation run.

    Args:
        websocket: WebSocket connection.
        run_id: Simulation run identifier.
    """

    await websocket.accept()
    service = get_simulation_service()
    try:
        events = service.list_events(run_id)
    except KeyError:
        await websocket.send_json(
            {"type": "error", "detail": "Simulation run not found."}
        )
        await websocket.close()
        return
    await websocket.send_json(
        {
            "type": "snapshot",
            "run_id": str(run_id),
            "events": jsonable_encoder(events),
        }
    )
    await websocket.close()
