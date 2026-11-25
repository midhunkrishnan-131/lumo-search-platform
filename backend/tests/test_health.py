"""Health, readiness, and error-response tests."""


def test_versioned_health_endpoint(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "LUMO",
        "version": "0.1.0",
    }


def test_health_alias_matches_existing_settings_page(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["application"] == "LUMO"


def test_readiness_reports_database_without_internal_details(client):
    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    body = response.json()
    assert body == {
        "status": "not_ready",
        "application": "LUMO",
        "checks": {"database": "unavailable"},
    }
    assert "postgres" not in response.text.lower()
    assert "change-me" not in response.text


def test_unknown_route_returns_404(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


def test_unhandled_errors_hide_exception_text(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings)

    @app.get("/api/v1/_test_error")
    def _test_error() -> None:
        raise RuntimeError("super-secret-password")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/_test_error")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "super-secret-password" not in response.text


def test_validation_errors_stay_422(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings)

    @app.get("/api/v1/_test_validation")
    def _test_validation(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/_test_validation?count=nope")

    assert response.status_code == 422
