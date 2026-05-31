"""Tests for runtime job and watchdog control-plane APIs."""

import csv
from pathlib import Path

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
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def create_test_client() -> TestClient:
    """Create a FastAPI test client with fresh in-memory state.

    Returns:
        Test client for the API app.
    """

    reset_simulation_service()
    return TestClient(create_app())


def write_candle_csv(path: Path) -> None:
    """Write a valid candle CSV fixture.

    Args:
        path: Destination CSV path.
    """

    row = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-01-01T01:00:00Z",
        "open": "100",
        "high": "110",
        "low": "90",
        "close": "105",
        "volume": "2.5",
        "quote_volume": "262.5",
        "source": "fixture",
        "as_of": "2026-01-01T01:00:00Z",
        "created_at": "2026-01-01T01:00:00Z",
    }
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def queue_experiment_run(client: TestClient, path: Path) -> str:
    """Create a dataset, create an experiment, and queue its run.

    Args:
        client: Test client.
        path: CSV fixture path.

    Returns:
        Runtime job identifier.
    """

    upload_response = client.post(
        "/api/datasets/upload",
        json={"name": "fixture candles", "source_path": str(path)},
        headers=RESEARCHER_HEADERS,
    )
    assert upload_response.status_code == 200
    dataset_id = upload_response.json()["dataset_id"]
    create_response = client.post(
        "/api/experiments",
        json={
            "name": "runtime experiment",
            "kind": "backtest",
            "hypothesis": "Runtime job is queued.",
            "dataset_id": dataset_id,
            "parameters": {},
        },
        headers=RESEARCHER_HEADERS,
    )
    assert create_response.status_code == 200
    experiment_id = create_response.json()["experiment_id"]
    run_response = client.post(
        f"/api/experiments/{experiment_id}/run",
        headers=RESEARCHER_HEADERS,
    )
    assert run_response.status_code == 200
    return str(run_response.json()["metrics"]["job_id"])


def test_experiment_run_creates_runtime_job(tmp_path: Path) -> None:
    """Verify queued experiment runs create runtime jobs."""

    client = create_test_client()
    path = tmp_path / "candles.csv"
    write_candle_csv(path)

    job_id = queue_experiment_run(client, path)
    jobs_response = client.get("/api/runtime/jobs")
    job_response = client.get(f"/api/runtime/jobs/{job_id}")
    unknown_response = client.get(f"/api/runtime/jobs/{UNKNOWN_ID}")
    watchdog_response = client.post(
        "/api/runtime/watchdog",
        headers=OPERATOR_HEADERS,
    )

    assert jobs_response.status_code == 200
    assert len(jobs_response.json()) == 1
    assert job_response.status_code == 200
    job = job_response.json()
    assert job["job_type"] == "experiment_run"
    assert job["status"] == "queued"
    assert job["resource_type"] == "experiment"
    assert unknown_response.status_code == 404
    assert watchdog_response.status_code == 200
    watchdog = watchdog_response.json()
    assert watchdog["worker_status"] == "missing"
    assert watchdog["queued_job_count"] == 1
    assert "queued_work_without_healthy_worker" in {
        check["code"] for check in watchdog["checks"]
    }


def test_runtime_heartbeat_and_watchdog_rbac_and_audit() -> None:
    """Verify runtime heartbeat RBAC, watchdog output, and audit entries."""

    client = create_test_client()

    viewer_response = client.post(
        "/api/runtime/heartbeats",
        json={"worker_name": "backtest-worker"},
        headers=VIEWER_HEADERS,
    )
    missing_report_response = client.post(
        "/api/runtime/watchdog",
        headers=OPERATOR_HEADERS,
    )
    heartbeat_response = client.post(
        "/api/runtime/heartbeats",
        json={
            "worker_name": "backtest-worker",
            "worker_status": "healthy",
            "event_queue_depth": 4,
            "clock_lag_ms": 120,
        },
        headers=OPERATOR_HEADERS,
    )
    healthy_report_response = client.post(
        "/api/runtime/watchdog",
        headers=OPERATOR_HEADERS,
    )
    heartbeats_response = client.get("/api/runtime/heartbeats")

    assert viewer_response.status_code == 403
    assert missing_report_response.status_code == 200
    assert missing_report_response.json()["worker_status"] == "missing"
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["worker_status"] == "healthy"
    assert heartbeats_response.status_code == 200
    assert heartbeats_response.json()[0]["worker_name"] == "backtest-worker"
    assert healthy_report_response.status_code == 200
    healthy_report = healthy_report_response.json()
    assert healthy_report["worker_status"] == "healthy"
    assert healthy_report["checks"][0]["code"] == "runtime_healthy"

    audit_response = client.get("/api/audit/logs", headers=ADMIN_HEADERS)
    assert [entry["action"] for entry in audit_response.json()] == [
        "runtime.watchdog.run",
        "runtime.heartbeat.record",
        "runtime.watchdog.run",
    ]
