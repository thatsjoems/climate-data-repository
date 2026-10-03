"""
Public health-check endpoint tests (items 1 and 7 of the September 2026 external review).

Item 1: the database exception must never appear in the response body (only in
server-side logs) - this is a public, unauthenticated endpoint.
Item 7: /api/health now reports a coarse "environment" label so the frontend
can decide whether to show demo account credentials on the login page.
"""
import app.main as main_module


def test_health_reports_ok_when_the_database_is_reachable(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "environment" in body


def test_health_never_leaks_the_database_exception_into_the_response(client, monkeypatch):
    class ExplodingSession:
        def execute(self, *a, **kw):
            raise RuntimeError("connection to server at \"internal-db-host.private\" failed: password authentication failed")
        def close(self):
            pass

    monkeypatch.setattr(main_module, "SessionLocal", lambda: ExplodingSession())
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unreachable"
    # The exception text (host, credentials, driver detail) must never appear anywhere in the body.
    raw = res.text
    assert "internal-db-host" not in raw
    assert "password authentication" not in raw
    assert "RuntimeError" not in raw


def test_health_environment_label_reflects_settings(client, monkeypatch):
    monkeypatch.setattr(main_module.settings, "ENVIRONMENT", "production")
    assert client.get("/api/health").json()["environment"] == "production"
    monkeypatch.setattr(main_module.settings, "ENVIRONMENT", "development")
    assert client.get("/api/health").json()["environment"] == "development"
