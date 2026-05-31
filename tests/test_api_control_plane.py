"""Smoke tests for the FastAPI simulation control plane."""

from fastapi.testclient import TestClient

from tiko.api.dependencies import reset_simulation_service
from tiko.api.main import create_app


def create_test_client() -> TestClient:
    """Create a FastAPI test client with fresh in-memory state.

    Returns:
        Test client for the API app.
    """

    reset_simulation_service()
    return TestClient(create_app())


def test_health_route_reports_simulation_safety_mode() -> None:
    """Verify health route exposes safety boundaries without trading capability."""

    client = create_test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["safety_mode"] == "simulation_only"
    assert payload["private_exchange_methods_allowed"] is False
    assert payload["trading_credentials_allowed"] is False


def test_simulation_routes_create_and_step_run() -> None:
    """Verify simulation routes create a run and advance simulated execution."""

    client = create_test_client()
    create_response = client.post(
        "/api/simulations",
        json={
            "name": "api-demo",
            "symbols": ["BTCUSDT"],
            "start_sim_time": "2026-01-01T00:00:00Z",
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    step_response = client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
    )

    assert step_response.status_code == 200
    step_payload = step_response.json()
    assert step_payload["risk_review"]["status"] == "approved"
    assert step_payload["order"]["status"] == "filled"
    assert step_payload["fill"]["symbol"] == "BTCUSDT"

    list_response = client.get("/api/simulations")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_query_routes_expose_simulated_state() -> None:
    """Verify query routes expose decisions, orders, fills, portfolio, and risk."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "query-demo", "symbols": ["BTCUSDT"]},
    ).json()["run_id"]
    client.post(f"/api/simulations/{run_id}/step", json={"confidence": 0.7})

    assert client.get("/api/market/symbols").json()["private_methods_allowed"] is False
    assert len(client.get("/api/decisions").json()) == 1
    assert len(client.get("/api/orders").json()) == 1
    assert len(client.get("/api/fills").json()) == 1
    assert len(client.get(f"/api/simulations/{run_id}/events").json()) == 1
    observation_response = client.get(f"/api/simulations/{run_id}/observations/BTCUSDT")
    assert observation_response.status_code == 200
    observation_payload = observation_response.json()
    assert observation_payload["symbol"] == "BTCUSDT"
    assert len(observation_payload["candles"]) == 1
    assert client.get(f"/api/portfolio/{run_id}/summary").json()["run_id"] == run_id
    assert (
        client.get(f"/api/risk/{run_id}/limits").json()["live_trading_allowed"] is False
    )
    assert (
        client.get(f"/api/risk/{run_id}/reviews/latest").json()["status"] == "approved"
    )


def test_agent_routes_evaluate_rule_based_agent() -> None:
    """Verify agent routes expose deterministic structured intent."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "agent-demo", "symbols": ["BTCUSDT"]},
    ).json()["run_id"]
    client.post(f"/api/simulations/{run_id}/step", json={"confidence": 0.7})
    observation = client.get(f"/api/simulations/{run_id}/observations/BTCUSDT").json()

    agents_response = client.get("/api/agents")
    intent_response = client.post("/api/agents/rule-based/evaluate", json=observation)

    assert agents_response.status_code == 200
    assert agents_response.json()[0]["live_trading_allowed"] is False
    assert intent_response.status_code == 200
    intent_payload = intent_response.json()
    assert intent_payload["run_id"] == run_id
    assert intent_payload["symbol"] == "BTCUSDT"
    assert intent_payload["action"] == "hold"


def test_simulation_websocket_returns_event_snapshot() -> None:
    """Verify WebSocket route returns current simulation events."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-demo", "symbols": ["BTCUSDT"]},
    ).json()["run_id"]
    client.post(f"/api/simulations/{run_id}/step", json={"confidence": 0.7})

    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "snapshot"
    assert payload["run_id"] == run_id
    assert len(payload["events"]) == 1


def test_run_specific_routes_return_404_for_unknown_run() -> None:
    """Verify run-specific routes return clear not-found responses."""

    client = create_test_client()
    unknown_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(f"/api/simulations/{unknown_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Simulation run not found."
