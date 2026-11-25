"""Contract test for the existing frontend health check.

The settings page fetches GET {apiBaseUrl}/health with Accept: application/json.
The versioned endpoint used by later API calls is GET /api/v1/health.
Both must succeed from the Vite dev origins without changing the homepage.
"""


def test_frontend_can_call_versioned_health(client):
    response = client.get(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "LUMO",
        "version": "0.1.0",
    }
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_settings_page_health_check_is_allowed(client):
    response = client.get(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.json()["status"] == "healthy"


def test_preflight_from_frontend_origin(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Accept",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    allow_methods = response.headers["access-control-allow-methods"]
    assert "GET" in allow_methods
    assert "POST" in allow_methods


def test_unknown_origin_is_not_granted_cors(client):
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
