"""Smoke tests for the foundation health check."""


def test_health_endpoint_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "KisanProcure API"
    assert data["environment"] == "testing"
    assert data["database"] == "ok"
    assert data["version"]


def test_health_endpoint_accepts_trailing_slash(client):
    response = client.get("/api/health/")
    assert response.status_code == 200


def test_index_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"KisanProcure" in response.data
    assert b"/api/health" in response.data
    # Landing page must expose login/register navigation.

    assert b"/login" in response.data
    assert b"/register" in response.data


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"KisanProcure" in response.data
    assert b"loginForm" in response.data
    assert b"kp_access_token" in response.data


def test_register_page_renders(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"KisanProcure" in response.data
    assert b"registerForm" in response.data


def test_unknown_route_returns_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404