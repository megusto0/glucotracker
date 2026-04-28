"""Authentication tests for protected REST endpoints."""

from fastapi.testclient import TestClient

from glucotracker.main import app


def test_meals_requires_token(api_client: TestClient) -> None:
    """Protected endpoints reject requests without a bearer token."""
    response = api_client.get("/meals", headers={"Authorization": ""})

    assert response.status_code == 401


def test_meals_accepts_correct_token(api_client: TestClient) -> None:
    """Protected endpoints accept the configured bearer token."""
    response = api_client.get("/meals")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_health_and_openapi_do_not_require_token() -> None:
    """Health and OpenAPI remain public."""
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200
