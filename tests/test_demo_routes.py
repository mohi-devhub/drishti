from fastapi.testclient import TestClient

from drishti.app import create_app
from drishti.config import get_settings


def test_demo_token_returns_local_jwt(monkeypatch) -> None:
    monkeypatch.setenv("DRISHTI_ENV", "local")
    monkeypatch.setenv("DRISHTI_TEST_JWT_SECRET", "demo-secret-with-at-least-thirty-two-bytes")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://issuer.test")
    monkeypatch.setenv("CLERK_JWT_AUDIENCE", "drishti")
    get_settings.cache_clear()

    client = TestClient(create_app())

    response = client.get("/demo/token/merchant_c")

    assert response.status_code == 200
    assert response.json()["merchant_key"] == "merchant_c"
    assert response.json()["token"]

    get_settings.cache_clear()


def test_cors_preflight_skips_auth(monkeypatch) -> None:
    monkeypatch.setenv("DRISHTI_ENV", "local")
    monkeypatch.setenv("DRISHTI_TEST_JWT_SECRET", "demo-secret-with-at-least-thirty-two-bytes")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://issuer.test")
    monkeypatch.setenv("CLERK_JWT_AUDIENCE", "drishti")
    monkeypatch.setenv("DRISHTI_WEB_ORIGIN", "http://localhost:3000")
    get_settings.cache_clear()

    client = TestClient(create_app())

    response = client.options(
        "/api/findings",
        headers={
            "origin": "http://localhost:3000",
            "access-control-request-method": "GET",
            "access-control-request-headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    get_settings.cache_clear()
