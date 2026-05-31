"""Smoke tests for the FastAPI simulation control plane."""

from fastapi.testclient import TestClient

from tiko.api.dependencies import reset_simulation_service
from tiko.api.main import create_app

ADMIN_HEADERS = {"X-Tiko-Role": "admin", "X-Tiko-User": "admin@example.test"}
OPERATOR_HEADERS = {"X-Tiko-Role": "operator", "X-Tiko-User": "operator@example.test"}
RESEARCHER_HEADERS = {
    "X-Tiko-Role": "researcher",
    "X-Tiko-User": "researcher@example.test",
}
VIEWER_HEADERS = {"X-Tiko-Role": "viewer", "X-Tiko-User": "viewer@example.test"}


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
        headers=OPERATOR_HEADERS,
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    step_response = client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    assert step_response.status_code == 200
    step_payload = step_response.json()
    assert step_payload["risk_review"]["status"] == "approved"
    assert step_payload["order"]["status"] == "filled"
    assert step_payload["fill"]["symbol"] == "BTCUSDT"

    list_response = client.get("/api/simulations")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_comparison_routes_benchmark_and_compare_runs() -> None:
    """Verify comparison routes expose deterministic benchmark tooling."""

    client = create_test_client()
    first_run_id = client.post(
        "/api/simulations",
        json={
            "name": "first",
            "symbols": ["BTCUSDT"],
            "start_sim_time": "2026-01-01T00:00:00Z",
        },
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    second_run_id = client.post(
        "/api/simulations",
        json={
            "name": "second",
            "symbols": ["BTCUSDT"],
            "start_sim_time": "2026-01-01T00:00:00Z",
        },
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{first_run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    client.post(
        f"/api/simulations/{second_run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    benchmark_response = client.get(f"/api/comparisons/runs/{first_run_id}/benchmark")
    comparison_response = client.post(
        "/api/comparisons/runs",
        json={
            "baseline_run_id": first_run_id,
            "candidate_run_id": second_run_id,
        },
        headers=RESEARCHER_HEADERS,
    )

    assert benchmark_response.status_code == 200
    assert benchmark_response.json()["fill_count"] == 1
    assert comparison_response.status_code == 200
    assert comparison_response.json()["fingerprints_match"] is True


def test_query_routes_expose_simulated_state() -> None:
    """Verify query routes expose decisions, orders, fills, portfolio, and risk."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "query-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

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
    report_response = client.post(
        f"/api/reports/simulations/{run_id}",
        headers=OPERATOR_HEADERS,
    )
    alert_response = client.post(
        f"/api/risk/{run_id}/alerts",
        json={
            "category": "drawdown",
            "severity": "warning",
            "message": "Drawdown near threshold.",
        },
        headers=OPERATOR_HEADERS,
    )

    assert report_response.status_code == 200
    assert report_response.json()["report_type"] == "simulation"
    assert len(client.get(f"/api/reports/simulations/{run_id}").json()) == 1
    assert alert_response.status_code == 200
    alert_id = alert_response.json()["alert_id"]
    assert client.get(f"/api/risk/{run_id}/alerts").json()[0]["status"] == "open"
    assert (
        client.post(
            f"/api/risk/{run_id}/alerts/{alert_id}/status",
            json={"status": "acknowledged"},
            headers=OPERATOR_HEADERS,
        ).json()["status"]
        == "acknowledged"
    )
    decision_id = client.get("/api/decisions").json()[0]["decision_id"]
    review_response = client.post(
        f"/api/decisions/{decision_id}/review",
        json={
            "horizon": "1h",
            "realized_return": "0.01",
            "max_adverse_excursion": "-0.002",
            "max_favorable_excursion": "0.014",
            "was_correct_directionally": True,
            "error_tags": [],
            "reviewer_summary": "Decision remained directionally correct.",
        },
        headers=RESEARCHER_HEADERS,
    )
    memory_response = client.post(
        f"/api/simulations/{run_id}/memory",
        json={
            "memory_type": "decision",
            "summary": "Decision review memory.",
            "content": {"decision_id": decision_id},
            "tags": ["posterior_review"],
            "decision_id": decision_id,
        },
        headers=RESEARCHER_HEADERS,
    )

    assert review_response.status_code == 200
    assert review_response.json()["decision_id"] == decision_id
    assert (
        client.get(f"/api/decisions/{decision_id}/review").json()[0]["horizon"] == "1h"
    )
    assert memory_response.status_code == 200
    assert (
        client.get(f"/api/simulations/{run_id}/memory").json()[0]["memory_type"]
        == "decision"
    )


def test_agent_routes_evaluate_rule_based_agent() -> None:
    """Verify agent routes expose deterministic structured intent."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "agent-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
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


def test_model_registry_routes_manage_research_models() -> None:
    """Verify model registry routes manage advisory research models."""

    client = create_test_client()
    training_dataset_id = "00000000-0000-4000-8000-000000000901"
    validation_dataset_id = "00000000-0000-4000-8000-000000000902"

    create_response = client.post(
        "/api/models",
        json={
            "name": "baseline-rl",
            "version": "0.1.0",
            "model_type": "rl",
            "algorithm": "discrete_policy",
            "training_dataset_id": training_dataset_id,
            "validation_dataset_id": validation_dataset_id,
            "metrics": {"reward": "0.12"},
            "artifact_uri": "memory://baseline-rl",
            "status": "draft",
        },
        headers=RESEARCHER_HEADERS,
    )

    assert create_response.status_code == 200
    model_id = create_response.json()["model_id"]
    assert client.get("/api/models").json()[0]["model_id"] == model_id
    assert client.get(f"/api/models/{model_id}").json()["status"] == "draft"

    status_response = client.post(
        f"/api/models/{model_id}/status",
        json={"status": "validated"},
        headers=RESEARCHER_HEADERS,
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "validated"
    assert (
        client.get("/api/models/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )


def test_plugin_registry_routes_validate_sandbox_policy() -> None:
    """Verify plugin registry routes accept safe manifests and reject unsafe ones."""

    client = create_test_client()
    safe_manifest = {
        "name": "synthetic_liquidity_shock_generator",
        "version": "0.1.0",
        "plugin_type": "event_generation",
        "description": "Generate synthetic liquidity shocks for simulations.",
        "permissions": {"write_market_events": True},
        "inputs": ["run_id", "symbols"],
        "output_schema": "MarketEvent",
        "tests": ["test_schema_valid"],
    }

    create_response = client.post(
        "/api/plugins",
        json=safe_manifest,
        headers=RESEARCHER_HEADERS,
    )

    assert create_response.status_code == 200
    plugin_id = create_response.json()["plugin_id"]
    assert client.get("/api/plugins").json()[0]["plugin_id"] == plugin_id
    assert client.get(f"/api/plugins/{plugin_id}").json()["status"] == "validated"
    assert (
        client.post(
            f"/api/plugins/{plugin_id}/status",
            json={"status": "enabled"},
            headers=RESEARCHER_HEADERS,
        ).json()["status"]
        == "enabled"
    )

    unsafe_manifest = safe_manifest | {
        "permissions": {"write_market_events": True, "write_orders": True}
    }
    unsafe_response = client.post(
        "/api/plugins",
        json=unsafe_manifest,
        headers=RESEARCHER_HEADERS,
    )

    assert unsafe_response.status_code == 422
    assert "write_orders" in unsafe_response.json()["detail"]


def test_simulation_websocket_returns_event_snapshot() -> None:
    """Verify WebSocket route returns current simulation events."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

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


def test_memory_route_rejects_cross_run_decision_reference() -> None:
    """Verify memory entries cannot reference a decision from another run."""

    client = create_test_client()
    first_run_id = client.post(
        "/api/simulations",
        json={"name": "first", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    second_run_id = client.post(
        "/api/simulations",
        json={"name": "second", "symbols": ["ETHUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{first_run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    decision_id = client.get("/api/decisions").json()[0]["decision_id"]

    response = client.post(
        f"/api/simulations/{second_run_id}/memory",
        json={
            "memory_type": "decision",
            "summary": "Invalid memory.",
            "content": {},
            "tags": [],
            "decision_id": decision_id,
        },
        headers=RESEARCHER_HEADERS,
    )

    assert response.status_code == 422
    assert "must belong to the run" in response.json()["detail"]


def test_rbac_rejects_viewer_default_and_invalid_role_mutations() -> None:
    """Verify unsafe roles cannot mutate control-plane simulation state."""

    client = create_test_client()
    payload = {"name": "blocked", "symbols": ["BTCUSDT"]}

    default_role_response = client.post("/api/simulations", json=payload)
    viewer_response = client.post(
        "/api/simulations",
        json=payload,
        headers=VIEWER_HEADERS,
    )
    invalid_role_response = client.post(
        "/api/simulations",
        json=payload,
        headers={"X-Tiko-Role": "trader", "X-Tiko-User": "invalid@example.test"},
    )

    assert default_role_response.status_code == 403
    assert viewer_response.status_code == 403
    assert invalid_role_response.status_code == 401


def test_audit_logs_authorized_control_plane_mutations() -> None:
    """Verify successful protected mutations are available to audit readers."""

    client = create_test_client()
    create_response = client.post(
        "/api/simulations",
        json={"name": "audit-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    )
    run_id = create_response.json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    viewer_response = client.get("/api/audit/logs", headers=VIEWER_HEADERS)
    admin_response = client.get("/api/audit/logs", headers=ADMIN_HEADERS)

    assert viewer_response.status_code == 403
    assert admin_response.status_code == 200
    entries = admin_response.json()
    assert [entry["action"] for entry in entries] == [
        "simulation.create",
        "simulation.step",
    ]
    assert {entry["role"] for entry in entries} == {"operator"}
    assert {entry["user_id"] for entry in entries} == {"operator@example.test"}
