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
    assert body["version"].startswith("0.")
    assert body["db"] == "not_checked"
    assert "commit" in body
    assert "commit_short" in body


def test_version_and_commit_endpoints() -> None:
    client = TestClient(app)

    for path in ("/version", "/commit"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "glucotracker"
        assert body["version"].startswith("0.")
        assert "commit" in body
        assert "commit_short" in body
