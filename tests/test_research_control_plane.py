"""Tests for dataset and experiment control-plane APIs."""

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from tiko.api.dependencies import reset_simulation_service
from tiko.api.main import create_app

ADMIN_HEADERS = {"X-Tiko-Role": "admin", "X-Tiko-User": "admin@example.test"}
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


def sample_candle_row() -> dict[str, str]:
    """Create a normalized candle CSV row.

    Returns:
        Raw CSV row with required candle fields.
    """

    return {
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


def write_candle_csv(path: Path) -> None:
    """Write a valid candle CSV fixture.

    Args:
        path: Destination CSV path.
    """

    row = sample_candle_row()
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def upload_dataset(client: TestClient, path: Path) -> str:
    """Upload a valid dataset fixture.

    Args:
        client: Test client.
        path: CSV fixture path.

    Returns:
        Dataset identifier.
    """

    response = client.post(
        "/api/datasets/upload",
        json={"name": "fixture candles", "source_path": str(path)},
        headers=RESEARCHER_HEADERS,
    )
    assert response.status_code == 200
    return response.json()["dataset_id"]


def test_dataset_routes_upload_validate_quality_and_candles(
    tmp_path: Path,
) -> None:
    """Verify dataset routes import, validate, expose quality, and audit."""

    client = create_test_client()
    path = tmp_path / "candles.csv"
    write_candle_csv(path)

    upload_response = client.post(
        "/api/datasets/upload",
        json={"name": "BTC fixture", "source_path": str(path)},
        headers=RESEARCHER_HEADERS,
    )
    assert upload_response.status_code == 200
    dataset = upload_response.json()
    dataset_id = dataset["dataset_id"]

    assert dataset["source"] == "csv"
    assert dataset["status"] == "validated"
    assert dataset["symbols"] == ["BTCUSDT"]
    assert dataset["timeframes"] == ["1h"]
    assert dataset["candle_count"] == 1
    assert len(client.get("/api/datasets").json()) == 1
    assert client.get(f"/api/datasets/{dataset_id}").json()["name"] == "BTC fixture"

    quality_response = client.get(f"/api/datasets/{dataset_id}/quality")
    candles_response = client.get(f"/api/datasets/{dataset_id}/candles")
    validate_response = client.post(
        f"/api/datasets/{dataset_id}/validate",
        headers=RESEARCHER_HEADERS,
    )

    assert quality_response.status_code == 200
    assert quality_response.json()["error_count"] == 0
    assert candles_response.status_code == 200
    assert candles_response.json()[0]["symbol"] == "BTCUSDT"
    assert validate_response.status_code == 200
    assert validate_response.json()["total_records"] == 1

    audit_response = client.get("/api/audit/logs", headers=ADMIN_HEADERS)
    assert [entry["action"] for entry in audit_response.json()] == [
        "dataset.upload",
        "dataset.validate",
    ]


def test_dataset_routes_reject_viewers_missing_files_and_unknown_ids(
    tmp_path: Path,
) -> None:
    """Verify dataset routes reject unauthorized and invalid requests."""

    client = create_test_client()
    path = tmp_path / "candles.csv"
    write_candle_csv(path)

    viewer_response = client.post(
        "/api/datasets/upload",
        json={"name": "blocked", "source_path": str(path)},
        headers=VIEWER_HEADERS,
    )
    missing_file_response = client.post(
        "/api/datasets/upload",
        json={"name": "missing", "source_path": str(tmp_path / "missing.csv")},
        headers=RESEARCHER_HEADERS,
    )

    assert viewer_response.status_code == 403
    assert missing_file_response.status_code == 422
    assert client.get(f"/api/datasets/{UNKNOWN_ID}").status_code == 404
    assert client.get(f"/api/datasets/{UNKNOWN_ID}/candles").status_code == 404


def test_experiment_routes_create_queue_and_audit(tmp_path: Path) -> None:
    """Verify experiment routes create draft records and queue runs."""

    client = create_test_client()
    path = tmp_path / "candles.csv"
    write_candle_csv(path)
    dataset_id = upload_dataset(client, path)

    create_response = client.post(
        "/api/experiments",
        json={
            "name": "baseline walk-forward",
            "kind": "walk_forward",
            "hypothesis": "Momentum survives validation splits.",
            "dataset_id": dataset_id,
            "parameters": {"splits": 3},
        },
        headers=RESEARCHER_HEADERS,
    )
    assert create_response.status_code == 200
    experiment = create_response.json()
    experiment_id = experiment["experiment_id"]

    assert experiment["status"] == "draft"
    assert client.get("/api/experiments").json()[0]["experiment_id"] == experiment_id
    assert client.get(f"/api/experiments/{experiment_id}").json()["kind"] == (
        "walk_forward"
    )

    run_response = client.post(
        f"/api/experiments/{experiment_id}/run",
        headers=RESEARCHER_HEADERS,
    )

    assert run_response.status_code == 200
    queued = run_response.json()
    assert queued["status"] == "queued"
    assert queued["queued_at"] is not None
    assert queued["metrics"]["queued"] is True

    audit_response = client.get("/api/audit/logs", headers=ADMIN_HEADERS)
    assert [entry["action"] for entry in audit_response.json()] == [
        "dataset.upload",
        "experiment.create",
        "experiment.run.queue",
    ]


def test_experiment_routes_reject_viewers_and_unknown_references(
    tmp_path: Path,
) -> None:
    """Verify experiment routes reject unauthorized and unknown resources."""

    client = create_test_client()
    path = tmp_path / "candles.csv"
    write_candle_csv(path)
    dataset_id = upload_dataset(client, path)
    create_payload = {
        "name": "blocked experiment",
        "kind": "backtest",
        "hypothesis": "Viewer cannot create experiments.",
        "dataset_id": dataset_id,
        "parameters": {},
    }

    viewer_response = client.post(
        "/api/experiments",
        json=create_payload,
        headers=VIEWER_HEADERS,
    )
    unknown_dataset_response = client.post(
        "/api/experiments",
        json=create_payload | {"dataset_id": UNKNOWN_ID},
        headers=RESEARCHER_HEADERS,
    )
    unknown_run_response = client.post(
        f"/api/experiments/{UNKNOWN_ID}/run",
        headers=RESEARCHER_HEADERS,
    )

    assert viewer_response.status_code == 403
    assert unknown_dataset_response.status_code == 404
    assert unknown_run_response.status_code == 404
