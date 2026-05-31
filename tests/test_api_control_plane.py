"""Smoke tests for the FastAPI simulation control plane."""

import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

import tiko.services.realtime as realtime_services
from tiko.api.dependencies import get_simulation_service, reset_simulation_service
from tiko.api.main import create_app
from tiko.api.routes import websocket as websocket_routes

ADMIN_HEADERS = {"X-Tiko-Role": "admin", "X-Tiko-User": "admin@example.test"}
OPERATOR_HEADERS = {"X-Tiko-Role": "operator", "X-Tiko-User": "operator@example.test"}
RESEARCHER_HEADERS = {
    "X-Tiko-Role": "researcher",
    "X-Tiko-User": "researcher@example.test",
}
VIEWER_HEADERS = {"X-Tiko-Role": "viewer", "X-Tiko-User": "viewer@example.test"}


class FakeRedisRuntime:
    """Fake Redis client that records API fanout publish calls."""

    def __init__(self) -> None:
        """Initialize the fake Redis runtime."""

        self.messages: list[tuple[str, str]] = []

    def ping(self) -> bool:
        """Return a successful connectivity result.

        Returns:
            Always `True` for API tests.
        """

        return True

    def publish(self, channel: str, message: str) -> int:
        """Record one published fanout message.

        Args:
            channel: Redis Pub/Sub channel.
            message: Serialized message payload.

        Returns:
            Simulated subscriber count.
        """

        self.messages.append((channel, message))
        return 1


class FakeRealtimeSubscription:
    """Fake live realtime subscription for WebSocket tests."""

    def __init__(self, events: list[dict[str, object]]) -> None:
        """Initialize the fake subscription.

        Args:
            events: Events returned to the WebSocket bridge.
        """

        self.events = list(events)
        self.closed = False

    def next_event(self, timeout_seconds: float = 1.0) -> dict[str, object] | None:
        """Return the next queued event.

        Args:
            timeout_seconds: Maximum blocking read duration in seconds.

        Returns:
            Next event or `None`.
        """

        if not self.events:
            return None
        return self.events.pop(0)

    def close(self) -> None:
        """Record that the subscription was closed."""

        self.closed = True


class FakeRealtimeSubscriberService:
    """Fake realtime subscriber service for WebSocket tests."""

    def __init__(self, subscription: FakeRealtimeSubscription | None) -> None:
        """Initialize the fake subscriber service.

        Args:
            subscription: Subscription returned by `subscribe`.
        """

        self.subscription = subscription
        self.subscribed_run_id: UUID | None = None
        self.subscribed_topics: tuple[str, ...] | None = None

    def subscribe(
        self,
        run_id: UUID,
        topics: Sequence[str],
    ) -> FakeRealtimeSubscription | None:
        """Record subscription arguments and return the configured subscription.

        Args:
            run_id: Simulation run identifier.
            topics: Requested realtime topics.

        Returns:
            Configured fake subscription.
        """

        self.subscribed_run_id = run_id
        self.subscribed_topics = tuple(topics)
        return self.subscription


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
    assert step_payload["portfolio_order_plan"]["status"] == "order_created"
    assert (
        step_payload["portfolio_order_plan"]["order_request"]["decision_id"]
        == (step_payload["decision"]["decision_id"])
    )
    assert Decimal(str(step_payload["portfolio_order_plan"]["expected_notional"])) > 0
    assert step_payload["order"]["status"] == "filled"
    assert step_payload["fill"]["symbol"] == "BTCUSDT"

    list_response = client.get("/api/simulations")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_configured_redis_url_publishes_api_step_fanout(monkeypatch) -> None:
    """Verify API runtime wires configured Redis fanout into simulation steps."""

    fake_redis = FakeRedisRuntime()
    monkeypatch.setenv("TIKO_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr(
        realtime_services.redis.Redis,
        "from_url",
        lambda redis_url, decode_responses: fake_redis,
    )
    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "redis-fanout-api", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]

    response = client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    topics = {
        str(json.loads(message)["topic"]) for _channel, message in fake_redis.messages
    }
    assert topics == {
        "agent.run",
        "decision.created",
        "fill.created",
        "market.candle",
        "order.updated",
        "portfolio.updated",
        "risk.reviewed",
        "simulation.heartbeat",
        "simulation.status",
    }
    assert all(
        channel.startswith(f"tiko:realtime:{run_id}:")
        for channel, _message in fake_redis.messages
    )


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


def test_simulation_lifecycle_routes_update_status_speed_and_audit() -> None:
    """Verify simulation lifecycle routes update run state and audit commands."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "lifecycle-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]

    viewer_response = client.post(
        f"/api/simulations/{run_id}/pause",
        headers=VIEWER_HEADERS,
    )
    start_response = client.post(
        f"/api/simulations/{run_id}/start",
        headers=OPERATOR_HEADERS,
    )
    pause_response = client.post(
        f"/api/simulations/{run_id}/pause",
        headers=OPERATOR_HEADERS,
    )
    resume_response = client.post(
        f"/api/simulations/{run_id}/resume",
        headers=OPERATOR_HEADERS,
    )
    speed_response = client.post(
        f"/api/simulations/{run_id}/speed",
        json={"speed_multiplier": "5"},
        headers=OPERATOR_HEADERS,
    )
    invalid_speed_response = client.post(
        f"/api/simulations/{run_id}/speed",
        json={"speed_multiplier": "0"},
        headers=OPERATOR_HEADERS,
    )
    risk_pause_response = client.post(
        f"/api/risk/{run_id}/pause",
        headers=OPERATOR_HEADERS,
    )
    risk_resume_response = client.post(
        f"/api/risk/{run_id}/resume",
        headers=OPERATOR_HEADERS,
    )
    stop_response = client.post(
        f"/api/simulations/{run_id}/stop",
        headers=OPERATOR_HEADERS,
    )
    status_response = client.get(f"/api/simulations/{run_id}/status")
    terminal_step_response = client.post(
        f"/api/simulations/{run_id}/step",
        headers=OPERATOR_HEADERS,
    )

    assert viewer_response.status_code == 403
    assert start_response.json()["status"] == "running"
    assert pause_response.json()["status"] == "paused"
    assert resume_response.json()["status"] == "running"
    assert speed_response.json()["speed_multiplier"] == "5"
    assert invalid_speed_response.status_code == 422
    assert risk_pause_response.status_code == 200
    assert risk_resume_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
    assert status_response.json()["status"] == "stopped"
    assert terminal_step_response.status_code == 422
    assert "stopped" in terminal_step_response.json()["detail"]
    assert (
        client.post(
            "/api/simulations/00000000-0000-0000-0000-000000000000/start",
            headers=OPERATOR_HEADERS,
        ).status_code
        == 404
    )

    audit_actions = [
        entry["action"]
        for entry in client.get("/api/audit/logs", headers=ADMIN_HEADERS).json()
    ]
    assert audit_actions == [
        "simulation.create",
        "simulation.start",
        "simulation.pause",
        "simulation.resume",
        "simulation.speed.update",
        "risk.pause",
        "risk.resume",
        "simulation.stop",
    ]


def test_simulation_create_accepts_configured_run_fields() -> None:
    """Verify simulation create route stores architecture config fields."""

    client = create_test_client()
    create_response = client.post(
        "/api/simulations",
        json={
            "name": "configured-create",
            "symbols": ["BTCUSDT"],
            "start_sim_time": "2026-01-01T00:00:00Z",
            "end_sim_time": "2026-01-01T01:00:00Z",
            "mode": "live_simulated_clock",
            "speed_multiplier": "4",
            "timeframe": "15m",
            "decision_interval": "30m",
            "initial_equity": "250000",
        },
        headers=OPERATOR_HEADERS,
    )
    invalid_response = client.post(
        "/api/simulations",
        json={
            "name": "invalid-end",
            "symbols": ["BTCUSDT"],
            "start_sim_time": "2026-01-01T00:00:00Z",
            "end_sim_time": "2026-01-01T00:00:00Z",
        },
        headers=OPERATOR_HEADERS,
    )
    invalid_equity_response = client.post(
        "/api/simulations",
        json={
            "name": "invalid-equity",
            "symbols": ["BTCUSDT"],
            "initial_equity": "0",
        },
        headers=OPERATOR_HEADERS,
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["mode"] == "live_simulated_clock"
    assert payload["speed_multiplier"] == "4"
    assert payload["end_sim_time"].startswith("2026-01-01T01:00:00")
    assert payload["account"]["initial_equity"] == "250000"
    assert payload["account"]["cash_balance"] == "250000"
    assert payload["account"]["total_equity"] == "250000"
    assert payload["config"]["timeframe"] == "15m"
    assert payload["config"]["decision_interval"] == "30m"
    assert payload["config"]["initial_equity"] == "250000"
    assert invalid_response.status_code == 422
    assert "end_sim_time" in invalid_response.json()["detail"]
    assert invalid_equity_response.status_code == 422


def test_simulation_create_uses_dataset_for_historical_replay(
    tmp_path: Path,
) -> None:
    """Verify simulation create route can use imported candles for replay."""

    client = create_test_client()
    valid_path = tmp_path / "valid-replay.csv"
    valid_path.write_text(
        "\n".join(
            [
                "symbol,timeframe,open_time,close_time,open,high,low,close,"
                "volume,quote_volume,source,as_of,created_at",
                "BTCUSDT,1h,2026-01-01T00:00:00Z,2026-01-01T01:00:00Z,"
                "100,110,95,105,2.5,262.5,csv,2026-01-01T01:00:00Z,"
                "2026-01-01T01:00:00Z",
            ]
        ),
        encoding="utf-8",
    )
    invalid_path = tmp_path / "invalid-replay.csv"
    invalid_path.write_text(
        "\n".join(
            [
                "symbol,timeframe,open_time,close_time,open,high,low,close,"
                "volume,quote_volume,source,as_of,created_at",
                "BTCUSDT,1h,2026-01-01T00:00:00Z,2026-01-01T01:00:00Z,"
                "100,90,95,105,2.5,262.5,csv,2026-01-01T01:00:00Z,"
                "2026-01-01T01:00:00Z",
            ]
        ),
        encoding="utf-8",
    )
    dataset_response = client.post(
        "/api/datasets/upload",
        json={"name": "valid replay", "source_path": str(valid_path)},
        headers=ADMIN_HEADERS,
    )
    invalid_dataset_response = client.post(
        "/api/datasets/upload",
        json={"name": "invalid replay", "source_path": str(invalid_path)},
        headers=ADMIN_HEADERS,
    )
    dataset_id = dataset_response.json()["dataset_id"]
    invalid_dataset_id = invalid_dataset_response.json()["dataset_id"]

    create_response = client.post(
        "/api/simulations",
        json={
            "name": "dataset-replay",
            "symbols": ["BTCUSDT"],
            "mode": "historical_replay",
            "dataset_id": dataset_id,
        },
        headers=OPERATOR_HEADERS,
    )
    missing_dataset_response = client.post(
        "/api/simulations",
        json={
            "name": "missing-replay-dataset",
            "symbols": ["BTCUSDT"],
            "mode": "historical_replay",
        },
        headers=OPERATOR_HEADERS,
    )
    unknown_dataset_response = client.post(
        "/api/simulations",
        json={
            "name": "unknown-replay-dataset",
            "symbols": ["BTCUSDT"],
            "mode": "historical_replay",
            "dataset_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=OPERATOR_HEADERS,
    )
    invalid_dataset_create_response = client.post(
        "/api/simulations",
        json={
            "name": "invalid-replay-dataset",
            "symbols": ["BTCUSDT"],
            "mode": "historical_replay",
            "dataset_id": invalid_dataset_id,
        },
        headers=OPERATOR_HEADERS,
    )

    assert dataset_response.status_code == 200
    assert invalid_dataset_response.status_code == 200
    assert invalid_dataset_response.json()["status"] == "invalid"
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["mode"] == "historical_replay"
    assert payload["start_sim_time"].startswith("2026-01-01T00:00:00")
    assert payload["config"]["data_source"] == "replay"
    step_response = client.post(
        f"/api/simulations/{payload['run_id']}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    assert step_response.status_code == 200
    assert step_response.json()["event"]["simulated_time"].startswith(
        "2026-01-01T01:00:00"
    )
    assert missing_dataset_response.status_code == 422
    assert "dataset_id" in missing_dataset_response.json()["detail"]
    assert unknown_dataset_response.status_code == 404
    assert invalid_dataset_create_response.status_code == 422
    assert "validated dataset" in invalid_dataset_create_response.json()["detail"]


def test_risk_limit_update_requires_operator_and_affects_reviews() -> None:
    """Verify risk limit updates are authorized, audited, and applied."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "risk-limit-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    request = {
        "minimum_confidence": 0.8,
        "minimum_data_quality_score": 0.9,
        "max_target_weight": "0.05",
        "min_order_notional": "5",
        "max_order_notional": "1000",
        "max_leverage": "2",
        "max_drawdown": "0.10",
        "max_daily_loss": "0.02",
    }

    viewer_response = client.put(
        f"/api/risk/{run_id}/limits",
        json=request,
        headers=VIEWER_HEADERS,
    )
    update_response = client.put(
        f"/api/risk/{run_id}/limits",
        json=request,
        headers=OPERATOR_HEADERS,
    )
    get_response = client.get(f"/api/risk/{run_id}/limits")
    unknown_response = client.put(
        "/api/risk/00000000-0000-0000-0000-000000000000/limits",
        json=request,
        headers=OPERATOR_HEADERS,
    )
    invalid_leverage_response = client.put(
        f"/api/risk/{run_id}/limits",
        json=request | {"max_leverage": "0"},
        headers=OPERATOR_HEADERS,
    )
    invalid_min_notional_response = client.put(
        f"/api/risk/{run_id}/limits",
        json=request | {"min_order_notional": "-1"},
        headers=OPERATOR_HEADERS,
    )
    step_response = client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.95},
        headers=OPERATOR_HEADERS,
    )
    review_response = client.get(f"/api/risk/{run_id}/reviews/latest")

    assert viewer_response.status_code == 403
    assert update_response.status_code == 200
    assert get_response.status_code == 200
    assert unknown_response.status_code == 404
    assert update_response.json()["live_trading_allowed"] is False
    assert Decimal(str(get_response.json()["max_target_weight"])) == Decimal("0.05")
    assert Decimal(str(get_response.json()["min_order_notional"])) == Decimal("5")
    assert Decimal(str(get_response.json()["max_order_notional"])) == Decimal("1000")
    assert Decimal(str(get_response.json()["max_leverage"])) == Decimal("2")
    assert Decimal(str(get_response.json()["max_drawdown"])) == Decimal("0.10")
    assert Decimal(str(get_response.json()["max_daily_loss"])) == Decimal("0.02")
    assert invalid_leverage_response.status_code == 422
    assert invalid_min_notional_response.status_code == 422
    assert step_response.status_code == 200
    assert review_response.json()["status"] == "resized"
    assert Decimal(str(review_response.json()["approved_target_weight"])) == Decimal(
        "0.05"
    )
    assert review_response.json()["triggered_rules"] == ["max_target_weight"]
    audit_actions = [
        entry["action"]
        for entry in client.get("/api/audit/logs", headers=ADMIN_HEADERS).json()
    ]
    assert audit_actions == [
        "simulation.create",
        "risk.limits.update",
        "simulation.step",
    ]


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
    assert len(client.get(f"/api/market/candles?run_id={run_id}").json()) == 1
    assert len(client.get("/api/market/events").json()) == 1
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
    assert len(client.get(f"/api/risk/{run_id}/reviews").json()) == 1
    assert len(client.get(f"/api/portfolio/{run_id}/positions").json()) == 1
    assert len(client.get(f"/api/portfolio/{run_id}/snapshots").json()) == 1
    assert client.get(f"/api/portfolio/{run_id}/pnl").json()["run_id"] == run_id
    assert client.get(f"/api/portfolio/{run_id}/drawdown").json()["run_id"] == run_id
    inject_response = client.post(
        "/api/market/events/inject",
        json={
            "run_id": run_id,
            "type": "news_event",
            "symbol": "BTCUSDT",
            "payload": {"headline": "Synthetic macro headline."},
            "source": "manual",
        },
        headers=OPERATOR_HEADERS,
    )
    viewer_inject_response = client.post(
        "/api/market/events/inject",
        json={
            "run_id": run_id,
            "type": "news_event",
            "payload": {},
        },
        headers=VIEWER_HEADERS,
    )
    assert inject_response.status_code == 200
    assert inject_response.json()["type"] == "news_event"
    assert viewer_inject_response.status_code == 403
    assert len(client.get("/api/market/events").json()) == 2
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
    simulation_report_id = report_response.json()["report_id"]
    render_response = client.get(f"/api/reports/{simulation_report_id}/render")
    unsupported_render_response = client.get(
        f"/api/reports/{simulation_report_id}/render?format=html"
    )
    unknown_render_response = client.get(
        "/api/reports/00000000-0000-0000-0000-000000000000/render"
    )
    assert render_response.status_code == 200
    rendered_report = render_response.json()
    assert rendered_report["format"] == "markdown"
    assert rendered_report["report_type"] == "simulation"
    assert "# query-demo simulation report" in rendered_report["content"]
    assert "### Activity" in rendered_report["content"]
    assert unsupported_render_response.status_code == 422
    assert unknown_render_response.status_code == 404
    assert (
        client.get(f"/api/reports/{simulation_report_id}").json()["report_id"]
        == simulation_report_id
    )
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
    decision_response = client.get(f"/api/decisions/{decision_id}")
    trace_response = client.get(f"/api/decisions/{decision_id}/trace")

    assert decision_response.status_code == 200
    decision_payload = decision_response.json()
    assert decision_payload["decision_id"] == decision_id
    assert decision_payload["status"] == "converted_to_order"
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["decision"]["decision_id"] == decision_id
    assert trace_payload["decision"]["status"] == "converted_to_order"
    assert (
        decision_payload["observation_id"]
        == trace_payload["decision"]["observation_id"]
    )
    assert (
        decision_payload["agent_run_id"] == trace_payload["agent_run"]["agent_run_id"]
    )
    assert (
        decision_payload["input_data_as_of"]
        == trace_payload["decision"]["input_data_as_of"]
    )
    assert trace_payload["risk_review"]["status"] == "approved"
    assert trace_payload["order"]["status"] == "filled"
    assert trace_payload["fill"]["symbol"] == "BTCUSDT"
    order_id = trace_payload["order"]["order_id"]
    fill_id = trace_payload["fill"]["fill_id"]
    assert client.get(f"/api/orders/{order_id}").json()["order_id"] == order_id
    assert client.get(f"/api/fills/{fill_id}").json()["fill_id"] == fill_id
    assert (
        client.get("/api/orders/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )
    assert (
        client.post(
            f"/api/decisions/{decision_id}/annotate",
            json={"summary": "blocked"},
            headers=VIEWER_HEADERS,
        ).status_code
        == 403
    )
    annotation_response = client.post(
        f"/api/decisions/{decision_id}/annotate",
        json={
            "summary": "Trace annotation.",
            "content": {"note": "Risk and fill were reviewed."},
            "tags": ["trace"],
        },
        headers=RESEARCHER_HEADERS,
    )
    assert annotation_response.status_code == 200
    assert annotation_response.json()["memory_type"] == "decision"
    decision_report_response = client.post(
        f"/api/reports/decisions/{decision_id}",
        headers=OPERATOR_HEADERS,
    )
    assert decision_report_response.status_code == 200
    decision_report = decision_report_response.json()
    decision_render_response = client.get(
        f"/api/reports/{decision_report['report_id']}/render"
    )
    assert decision_report["report_type"] == "decision"
    assert decision_report["sections"]["decision"]["decision_id"] == decision_id
    assert decision_render_response.status_code == 200
    assert "decision report" in decision_render_response.json()["content"]
    assert "### Risk Review" in decision_render_response.json()["content"]
    assert (
        client.get(f"/api/reports/{decision_report['report_id']}").json()["report_type"]
        == "decision"
    )
    assert len(client.get(f"/api/reports/decisions/{decision_id}").json()) == 1
    assert (
        client.post(
            "/api/reports/decisions/00000000-0000-0000-0000-000000000000",
            headers=OPERATOR_HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.get("/api/decisions/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )
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
    assert client.get(f"/api/decisions/{decision_id}").json()["status"] == "reviewed"
    assert (
        client.get(f"/api/decisions/{decision_id}/review").json()[0]["horizon"] == "1h"
    )
    assert memory_response.status_code == 200
    memory_id = memory_response.json()["memory_id"]
    memory_search_response = client.get(
        f"/api/simulations/{run_id}/memory/search?query=decision%20review&limit=2"
    )
    memory_as_of_response = client.get(
        f"/api/simulations/{run_id}/memory/search"
        "?query=decision&as_of=2000-01-01T00:00:00Z"
    )
    memory_no_match_response = client.get(
        f"/api/simulations/{run_id}/memory/search?query=unmatched"
    )
    memory_blank_query_response = client.get(
        f"/api/simulations/{run_id}/memory/search?query="
    )
    memory_bad_limit_response = client.get(
        f"/api/simulations/{run_id}/memory/search?query=decision&limit=0"
    )
    memory_unknown_response = client.get(
        "/api/simulations/00000000-0000-0000-0000-000000000000/"
        "memory/search?query=decision"
    )
    assert memory_search_response.status_code == 200
    memory_search = memory_search_response.json()
    assert memory_search[0]["entry"]["memory_id"] == memory_id
    assert memory_search[0]["score"] == 1.0
    assert memory_search[0]["matched_terms"] == ["decision", "review"]
    assert memory_as_of_response.json() == []
    assert memory_no_match_response.json() == []
    assert memory_blank_query_response.status_code == 422
    assert memory_bad_limit_response.status_code == 422
    assert memory_unknown_response.status_code == 404
    assert (
        client.get(f"/api/simulations/{run_id}/memory").json()[0]["memory_type"]
        == "decision"
    )


def test_report_artifact_route_stores_rendered_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Verify report artifact route writes rendered reports and audits the action."""

    monkeypatch.setenv("TIKO_ARTIFACT_ROOT", str(tmp_path))
    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "artifact-api", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    report_id = client.post(
        f"/api/reports/simulations/{run_id}",
        headers=OPERATOR_HEADERS,
    ).json()["report_id"]

    viewer_response = client.post(
        f"/api/reports/{report_id}/artifact",
        headers=VIEWER_HEADERS,
    )
    artifact_response = client.post(
        f"/api/reports/{report_id}/artifact",
        headers=OPERATOR_HEADERS,
    )
    unknown_response = client.post(
        "/api/reports/00000000-0000-0000-0000-000000000000/artifact",
        headers=OPERATOR_HEADERS,
    )
    artifact_path = tmp_path / "reports" / f"{report_id}.md"

    assert viewer_response.status_code == 403
    assert artifact_response.status_code == 200
    artifact = artifact_response.json()
    assert artifact["report_id"] == report_id
    assert artifact["format"] == "markdown"
    assert artifact["size_bytes"] == artifact_path.stat().st_size
    assert "# artifact-api simulation report" in artifact_path.read_text(
        encoding="utf-8"
    )
    assert unknown_response.status_code == 404
    audit_actions = [
        entry["action"]
        for entry in client.get("/api/audit/logs", headers=ADMIN_HEADERS).json()
    ]
    assert audit_actions == [
        "simulation.create",
        "simulation.step",
        "report.simulation.create",
        "report.artifact.store",
    ]


def test_market_orderbook_route_returns_latest_snapshot_and_safe_empty() -> None:
    """Verify market order book route exposes simulated snapshots safely."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "orderbook-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    response = client.get(f"/api/market/orderbook?symbol=BTCUSDT&run_id={run_id}")
    unscoped_response = client.get("/api/market/orderbook?symbol=BTCUSDT")
    missing_response = client.get(
        f"/api/market/orderbook?symbol=ETHUSDT&run_id={run_id}"
    )
    unknown_run_response = client.get(
        "/api/market/orderbook?symbol=BTCUSDT"
        "&run_id=00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_policy"] == "read_only_simulated_orderbook_snapshot"
    assert payload["private_methods_allowed"] is False
    assert payload["run_id"] == run_id
    assert payload["bids"]
    assert payload["asks"]
    assert payload["mid_price"] == "50035"
    assert payload["spread_bps"] == "2"
    assert payload["depth_1pct_usd"] == "5003500"
    assert payload["source"] == "synthetic_orderbook"
    assert unscoped_response.json()["mid_price"] == payload["mid_price"]
    assert missing_response.status_code == 200
    assert missing_response.json()["data_policy"] == (
        "read_only_orderbook_snapshot_unavailable"
    )
    assert missing_response.json()["bids"] == []
    assert unknown_run_response.status_code == 404


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
    agent_runs_response = client.get("/api/agents/runs")
    intent_response = client.post("/api/agents/rule-based/evaluate", json=observation)

    assert agents_response.status_code == 200
    assert agents_response.json()[0]["live_trading_allowed"] is False
    assert agent_runs_response.status_code == 200
    agent_run_id = agent_runs_response.json()[0]["agent_run_id"]
    assert client.get(f"/api/agents/runs/{agent_run_id}").status_code == 200
    messages_response = client.get(f"/api/agents/runs/{agent_run_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "observation"
    assert [message["content"].get("agent_role") for message in messages[2:-1]] == [
        "coordinator",
        "market_regime",
        "technical",
        "derivatives",
        "event",
        "quant_rl",
        "trader",
        "portfolio",
    ]
    assert messages[-1]["role"] == "critic"
    assert (
        client.post(
            f"/api/agents/runs/{agent_run_id}/replay",
            headers=VIEWER_HEADERS,
        ).status_code
        == 403
    )
    replay_response = client.post(
        f"/api/agents/runs/{agent_run_id}/replay",
        headers=RESEARCHER_HEADERS,
    )
    assert replay_response.status_code == 200
    assert replay_response.json()["agent_id"] == "synthetic_trader"
    assert (
        client.get("/api/agents/runs/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )
    assert intent_response.status_code == 200
    intent_payload = intent_response.json()
    assert intent_payload["run_id"] == run_id
    assert intent_payload["symbol"] == "BTCUSDT"
    assert intent_payload["action"] == "hold"


def test_openrouter_agent_route_requires_key_and_research_permission(
    monkeypatch,
) -> None:
    """Verify OpenRouter route fails safely when no API key is configured."""

    monkeypatch.setenv("TIKO_OPENROUTER_API_KEY", "")
    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "openrouter-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    observation = client.get(f"/api/simulations/{run_id}/observations/BTCUSDT").json()

    agents_response = client.get("/api/agents")
    viewer_response = client.post(
        "/api/agents/openrouter/evaluate",
        json=observation,
        headers=VIEWER_HEADERS,
    )
    researcher_response = client.post(
        "/api/agents/openrouter/evaluate",
        json=observation,
        headers=RESEARCHER_HEADERS,
    )

    assert any(
        agent["agent_id"] == "openrouter_trader" for agent in agents_response.json()
    )
    assert viewer_response.status_code == 403
    assert researcher_response.status_code == 503
    assert researcher_response.json()["detail"] == (
        "OpenRouter API key is not configured."
    )


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
    viewer_promote_response = client.post(
        f"/api/models/{model_id}/promote",
        headers=VIEWER_HEADERS,
    )
    promote_response = client.post(
        f"/api/models/{model_id}/promote",
        headers=RESEARCHER_HEADERS,
    )
    archive_response = client.post(
        f"/api/models/{model_id}/archive",
        headers=RESEARCHER_HEADERS,
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "validated"
    assert viewer_promote_response.status_code == 403
    assert promote_response.status_code == 200
    assert promote_response.json()["status"] == "paper_enabled"
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"
    assert (
        client.get("/api/models/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )
    assert (
        client.post(
            "/api/models/00000000-0000-0000-0000-000000000000/promote",
            headers=RESEARCHER_HEADERS,
        ).status_code
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
        "permissions": {
            "write_market_events": True,
            "approved_directories": ["plugins/synthetic_liquidity_shock_generator"],
            "cpu_time_limit_seconds": 10,
            "memory_limit_mb": 128,
            "wall_time_limit_seconds": 30,
        },
        "inputs": ["run_id", "symbols", "current_sim_time", "seed"],
        "output_schema": "MarketEvent",
        "tests": [
            "test_schema_valid",
            "test_no_write_orders",
            "test_no_future_events",
            "test_deterministic_seed",
            "test_network_policy",
            "test_approved_directories",
            "test_resource_limits",
        ],
    }

    viewer_sandbox_response = client.post(
        "/api/plugins/sandbox-tests",
        json=safe_manifest,
        headers=VIEWER_HEADERS,
    )
    sandbox_response = client.post(
        "/api/plugins/sandbox-tests",
        json=safe_manifest,
        headers=RESEARCHER_HEADERS,
    )
    create_response = client.post(
        "/api/plugins",
        json=safe_manifest,
        headers=RESEARCHER_HEADERS,
    )

    assert viewer_sandbox_response.status_code == 403
    assert sandbox_response.status_code == 200
    sandbox_report = sandbox_response.json()
    assert sandbox_report["passed"] is True
    assert [result["name"] for result in sandbox_report["results"]] == [
        "test_schema_valid",
        "test_no_write_orders",
        "test_no_future_events",
        "test_deterministic_seed",
        "test_network_policy",
        "test_approved_directories",
        "test_resource_limits",
    ]
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
        "permissions": {
            "write_market_events": True,
            "write_orders": True,
            "approved_directories": ["plugins/synthetic_liquidity_shock_generator"],
            "cpu_time_limit_seconds": 10,
            "memory_limit_mb": 128,
            "wall_time_limit_seconds": 30,
        }
    }
    unsafe_response = client.post(
        "/api/plugins",
        json=unsafe_manifest,
        headers=RESEARCHER_HEADERS,
    )
    unsupported_response = client.post(
        "/api/plugins",
        json=safe_manifest | {"tests": ["test_schema_valid", "test_unknown_policy"]},
        headers=RESEARCHER_HEADERS,
    )
    unsupported_schema_response = client.post(
        "/api/plugins",
        json=safe_manifest | {"output_schema": "UnstructuredText"},
        headers=RESEARCHER_HEADERS,
    )

    assert unsafe_response.status_code == 422
    assert "write_orders" in unsafe_response.json()["detail"]
    assert unsupported_response.status_code == 422
    assert "Unsupported sandbox test" in unsupported_response.json()["detail"]
    assert unsupported_schema_response.status_code == 422
    assert "output_schema" in unsupported_schema_response.json()["detail"]


def test_simulation_websocket_replays_default_subscription() -> None:
    """Verify WebSocket route returns snapshot, replay events, and completion."""

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
        snapshot = websocket.receive_json()
        messages = [websocket.receive_json() for _index in range(10)]

    assert snapshot["type"] == "snapshot"
    assert snapshot["run_id"] == run_id
    assert len(snapshot["events"]) == 1
    event_topics = {
        message["topic"] for message in messages if message["type"] == "event"
    }
    assert event_topics == {
        "agent.run",
        "decision.created",
        "fill.created",
        "market.candle",
        "order.updated",
        "portfolio.updated",
        "risk.reviewed",
        "simulation.heartbeat",
        "simulation.status",
    }
    heartbeat = next(
        message
        for message in messages
        if message.get("topic") == "simulation.heartbeat"
    )
    assert heartbeat["payload"]["run_id"] == run_id
    assert heartbeat["payload"]["simulated_time"] == heartbeat["simulated_time"]
    assert heartbeat["payload"]["clock_lag_ms"] == 0
    assert heartbeat["payload"]["event_queue_depth"] == 0
    assert heartbeat["payload"]["worker_status"] == "healthy"
    assert isinstance(heartbeat["payload"]["wall_time"], str)
    assert messages[-1]["type"] == "replay_complete"


def test_simulation_websocket_filters_subscription_topics() -> None:
    """Verify WebSocket route filters replay envelopes by subscribed topics."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-filter-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    stored_event_ids = {
        str(event["topic"]): str(event["event_id"])
        for event in get_simulation_service().list_realtime_events(UUID(run_id))
        if event["topic"] in {"decision.created", "fill.created"}
    }

    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        websocket.send_json(
            {"type": "subscribe", "topics": ["decision.created", "fill.created"]}
        )
        snapshot = websocket.receive_json()
        first_event = websocket.receive_json()
        second_event = websocket.receive_json()
        completion = websocket.receive_json()
    first_event_ids = {
        first_event["topic"]: first_event["event_id"],
        second_event["topic"]: second_event["event_id"],
    }
    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        websocket.send_json(
            {"type": "subscribe", "topics": ["decision.created", "fill.created"]}
        )
        websocket.receive_json()
        reconnected_first_event = websocket.receive_json()
        reconnected_second_event = websocket.receive_json()
        websocket.receive_json()
    reconnected_event_ids = {
        reconnected_first_event["topic"]: reconnected_first_event["event_id"],
        reconnected_second_event["topic"]: reconnected_second_event["event_id"],
    }

    assert snapshot["topics"] == ["decision.created", "fill.created"]
    assert {first_event["topic"], second_event["topic"]} == {
        "decision.created",
        "fill.created",
    }
    assert first_event_ids == reconnected_event_ids
    assert first_event_ids == stored_event_ids
    assert completion["type"] == "replay_complete"


def test_simulation_websocket_replays_manual_market_event_topic() -> None:
    """Verify WebSocket replay exposes persisted manual market event envelopes."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-market-event-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    inject_response = client.post(
        "/api/market/events/inject",
        json={
            "run_id": run_id,
            "type": "news_event",
            "symbol": "BTCUSDT",
            "payload": {"headline": "Synthetic macro headline."},
            "source": "manual",
        },
        headers=OPERATOR_HEADERS,
    )
    stored_event = next(
        event
        for event in get_simulation_service().list_realtime_events(UUID(run_id))
        if event["topic"] == "market.event"
    )

    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        websocket.send_json({"type": "subscribe", "topics": ["market.event"]})
        snapshot = websocket.receive_json()
        replay_event = websocket.receive_json()
        completion = websocket.receive_json()

    assert inject_response.status_code == 200
    assert snapshot["topics"] == ["market.event"]
    assert replay_event["type"] == "event"
    assert replay_event["topic"] == "market.event"
    assert replay_event["event_id"] == stored_event["event_id"]
    assert replay_event["payload"]["event_id"] == inject_response.json()["event_id"]
    assert replay_event["payload"]["payload"]["headline"] == (
        "Synthetic macro headline."
    )
    assert completion["type"] == "replay_complete"


def test_simulation_websocket_streams_live_fanout_after_replay(monkeypatch) -> None:
    """Verify live WebSocket mode streams fanout events after recovery replay."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-live-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    live_envelope = {
        "event_id": "evt-live-decision",
        "topic": "decision.created",
        "run_id": run_id,
        "simulated_time": "2026-01-01T01:00:00+00:00",
        "payload": {"run_id": run_id, "decision_id": "decision-live"},
    }
    live_subscription = FakeRealtimeSubscription([live_envelope])
    subscriber_service = FakeRealtimeSubscriberService(live_subscription)
    monkeypatch.setattr(
        websocket_routes,
        "get_realtime_subscriber_service",
        lambda: subscriber_service,
    )

    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        websocket.send_json(
            {"type": "subscribe", "topics": ["decision.created"], "live": True}
        )
        snapshot = websocket.receive_json()
        replay_event = websocket.receive_json()
        replay_completion = websocket.receive_json()
        live_event = websocket.receive_json()
        websocket.send_json({"type": "close"})

    assert snapshot["topics"] == ["decision.created"]
    assert replay_event["type"] == "event"
    assert replay_event["topic"] == "decision.created"
    assert replay_completion["type"] == "replay_complete"
    assert live_event == {"type": "event", **live_envelope}
    assert subscriber_service.subscribed_run_id == UUID(run_id)
    assert subscriber_service.subscribed_topics == ("decision.created",)
    assert live_subscription.closed is True


def test_simulation_websocket_accepts_empty_subscription() -> None:
    """Verify empty topic subscriptions only return snapshot and completion."""

    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-empty-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        websocket.send_json({"type": "subscribe", "topics": []})
        snapshot = websocket.receive_json()
        completion = websocket.receive_json()

    assert snapshot["topics"] == []
    assert completion["type"] == "replay_complete"


def test_simulation_websocket_live_empty_subscription_skips_fanout(
    monkeypatch,
) -> None:
    """Verify empty live subscriptions do not open fanout subscriptions."""

    subscriber_service = FakeRealtimeSubscriberService(FakeRealtimeSubscription([]))
    monkeypatch.setattr(
        websocket_routes,
        "get_realtime_subscriber_service",
        lambda: subscriber_service,
    )
    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "ws-empty-live-demo", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )

    with client.websocket_connect(f"/ws/simulations/{run_id}") as websocket:
        websocket.send_json({"type": "subscribe", "topics": [], "live": True})
        snapshot = websocket.receive_json()
        completion = websocket.receive_json()

    assert snapshot["topics"] == []
    assert completion["type"] == "replay_complete"
    assert subscriber_service.subscribed_run_id is None
    assert subscriber_service.subscribed_topics is None


def test_configured_database_persists_api_state_after_cache_reset(
    tmp_path, monkeypatch
) -> None:
    """Verify configured API persistence survives service cache reset."""

    database_path = tmp_path / "api.sqlite"
    monkeypatch.setenv(
        "TIKO_DATABASE_URL",
        f"sqlite+pysqlite:///{database_path.as_posix()}",
    )
    client = create_test_client()
    run_id = client.post(
        "/api/simulations",
        json={"name": "persistent-api", "symbols": ["BTCUSDT"]},
        headers=OPERATOR_HEADERS,
    ).json()["run_id"]
    client.post(
        f"/api/simulations/{run_id}/step",
        json={"confidence": 0.7},
        headers=OPERATOR_HEADERS,
    )
    client.post(
        "/api/market/events/inject",
        json={
            "run_id": run_id,
            "type": "news_event",
            "symbol": "BTCUSDT",
            "payload": {"headline": "Synthetic restart event."},
            "source": "manual",
        },
        headers=OPERATOR_HEADERS,
    )
    model_id = client.post(
        "/api/models",
        json={
            "name": "persistent-rl",
            "version": "0.1.0",
            "model_type": "rl",
            "algorithm": "discrete_policy",
            "training_dataset_id": "00000000-0000-4000-8000-000000000901",
            "validation_dataset_id": "00000000-0000-4000-8000-000000000902",
            "metrics": {"reward": "0.12"},
            "artifact_uri": "memory://persistent-rl",
            "status": "draft",
        },
        headers=RESEARCHER_HEADERS,
    ).json()["model_id"]
    plugin_id = client.post(
        "/api/plugins",
        json={
            "name": "persistent_synthetic_event_generator",
            "version": "0.1.0",
            "plugin_type": "event_generation",
            "description": "Generate synthetic events for persisted API tests.",
            "permissions": {
                "write_market_events": True,
                "approved_directories": [
                    "plugins/persistent_synthetic_event_generator"
                ],
                "cpu_time_limit_seconds": 10,
                "memory_limit_mb": 128,
                "wall_time_limit_seconds": 30,
            },
            "inputs": ["run_id", "symbols"],
            "output_schema": "MarketEvent",
            "tests": ["test_schema_valid"],
        },
        headers=RESEARCHER_HEADERS,
    ).json()["plugin_id"]

    reset_simulation_service()
    persisted_client = TestClient(create_app())
    try:
        assert persisted_client.get("/api/simulations").json()[0]["run_id"] == run_id
        assert len(persisted_client.get("/api/decisions").json()) == 1
        assert len(persisted_client.get("/api/orders").json()) == 1
        assert len(persisted_client.get("/api/fills").json()) == 1
        assert len(persisted_client.get(f"/api/risk/{run_id}/reviews").json()) == 1
        assert len(persisted_client.get("/api/market/events").json()) == 2
        assert persisted_client.get(f"/api/models/{model_id}").json()["name"] == (
            "persistent-rl"
        )
        assert persisted_client.get(f"/api/plugins/{plugin_id}").json()["status"] == (
            "validated"
        )
    finally:
        reset_simulation_service()


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
