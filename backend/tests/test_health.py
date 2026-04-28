"""Health endpoint tests."""

from fastapi.testclient import TestClient

from glucotracker.main import app


def test_health_returns_ok() -> None:
    """The scaffolded service exposes a basic health check."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["db"] in {"ok", "unavailable"}
