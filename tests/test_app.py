from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_chat_api_requires_login(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "reviewer")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    client = TestClient(create_app())

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 401


def test_login_sets_cookie_and_health_reports_missing_index(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "reviewer")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    client = TestClient(create_app())

    login = client.post("/api/login", json={"username": "reviewer", "password": "secret"})
    health = client.get("/api/health")

    assert login.status_code == 200
    assert "session" in login.cookies
    assert health.status_code == 200
    assert health.json()["index_ready"] is False
