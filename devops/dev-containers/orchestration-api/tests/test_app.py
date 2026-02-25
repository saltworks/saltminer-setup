# tests/test_app.py
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure the orchestration-api package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars BEFORE importing the app
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("SETUP_REPO", "/fake/saltminer-setup")
os.environ.setdefault("SALTMINER_REPO", "/fake/saltminer")

from app import app as flask_app  # noqa: E402

TEST_KEY = "test-api-key"


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ── GET /api/status ───────────────────────────────────────────────────────────

class TestStatus:
    def test_returns_200(self, client):
        with patch("app.get_container_status", return_value="running"):
            resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_returns_status_dict(self, client):
        with patch("app.get_container_status", return_value="running"):
            data = json.loads(client.get("/api/status").data)
        assert "status" in data
        assert isinstance(data["status"], dict)

    def test_includes_all_services(self, client):
        with patch("app.get_container_status", return_value="running"):
            data = json.loads(client.get("/api/status").data)
        from config import ALL_DEBUG_SERVICES
        for svc in ALL_DEBUG_SERVICES:
            assert svc in data["status"]


# ── GET /api/services ─────────────────────────────────────────────────────────

class TestListServices:
    def test_returns_200(self, client):
        with patch("app.get_container_status", return_value="stopped"):
            resp = client.get("/api/services")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        with patch("app.get_container_status", return_value="stopped"):
            data = json.loads(client.get("/api/services").data)
        assert isinstance(data, list)

    def test_each_entry_has_required_fields(self, client):
        with patch("app.get_container_status", return_value="stopped"):
            data = json.loads(client.get("/api/services").data)
        for entry in data:
            assert "name" in entry
            assert "container" in entry
            assert "status" in entry


# ── POST /api/services/{name}/start ──────────────────────────────────────────

class TestStart:
    def test_requires_api_key(self, client):
        resp = client.post("/api/services/api/start")
        assert resp.status_code == 401

    def test_unknown_service_returns_404(self, client):
        resp = client.post(
            "/api/services/nonexistent/start",
            headers={"X-API-Key": TEST_KEY},
        )
        assert resp.status_code == 404

    def test_valid_start_returns_200(self, client):
        mock_result = MagicMock(returncode=0, stdout="Started", stderr="")
        with patch("app.run_compose", return_value=mock_result):
            resp = client.post(
                "/api/services/api/start",
                headers={"X-API-Key": TEST_KEY},
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_compose_failure_returns_ok_false(self, client):
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("app.run_compose", return_value=mock_result):
            resp = client.post(
                "/api/services/api/start",
                headers={"X-API-Key": TEST_KEY},
            )
        data = json.loads(resp.data)
        assert data["ok"] is False


# ── POST /api/services/{name}/stop ───────────────────────────────────────────

class TestStop:
    def test_requires_api_key(self, client):
        resp = client.post("/api/services/api/stop")
        assert resp.status_code == 401

    def test_valid_stop_returns_200(self, client):
        mock_result = MagicMock(returncode=0, stdout="Stopped", stderr="")
        with patch("app.run_compose", return_value=mock_result):
            resp = client.post(
                "/api/services/api/stop",
                headers={"X-API-Key": TEST_KEY},
            )
        assert resp.status_code == 200


# ── POST /api/services/{name}/rebuild ────────────────────────────────────────

class TestRebuild:
    def test_requires_api_key(self, client):
        resp = client.post("/api/services/api/rebuild")
        assert resp.status_code == 401

    def test_build_failure_returns_500(self, client):
        mock_fail = MagicMock(returncode=1, stdout="", stderr="build failed")
        with patch("subprocess.run", return_value=mock_fail):
            resp = client.post(
                "/api/services/api/rebuild",
                headers={"X-API-Key": TEST_KEY},
            )
        assert resp.status_code == 500

    def test_success_returns_200(self, client):
        mock_ok = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=mock_ok):
            with patch("app.run_compose", return_value=MagicMock(returncode=0, stdout="up", stderr="")):
                resp = client.post(
                    "/api/services/api/rebuild",
                    headers={"X-API-Key": TEST_KEY},
                )
        assert resp.status_code == 200


# ── POST /api/services/rebuild-all ───────────────────────────────────────────

class TestRebuildAll:
    def test_requires_api_key(self, client):
        resp = client.post("/api/services/rebuild-all")
        assert resp.status_code == 401

    def test_returns_builds_and_up_keys(self, client):
        mock_ok = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=mock_ok):
            with patch("app.run_compose", return_value=mock_ok):
                resp = client.post(
                    "/api/services/rebuild-all",
                    headers={"X-API-Key": TEST_KEY},
                )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "builds" in data
        assert "up" in data


# ── GET /api/services/{name}/logs ────────────────────────────────────────────

class TestLogs:
    def test_unknown_service_returns_404(self, client):
        resp = client.get("/api/services/nonexistent/logs")
        assert resp.status_code == 404

    def test_returns_logs(self, client):
        mock_result = MagicMock(returncode=0, stdout="line1\nline2\n", stderr="")
        with patch("app.run_compose", return_value=mock_result):
            resp = client.get("/api/services/api/logs?lines=50")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "logs" in data


# ── POST /api/ui/restart ─────────────────────────────────────────────────────

class TestUiRestart:
    def test_requires_api_key(self, client):
        resp = client.post("/api/ui/restart")
        assert resp.status_code == 401

    def test_restart_returns_200(self, client):
        mock_ok = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("app.run_compose", return_value=mock_ok):
            resp = client.post("/api/ui/restart", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200


# ── POST /api/repo/checkout/<branch> ─────────────────────────────────────────
# Branch is a URL path segment, no request body needed.

class TestCheckout:
    def test_requires_api_key(self, client):
        resp = client.post("/api/repo/checkout/main")
        assert resp.status_code == 401

    def test_success(self, client):
        mock_ok = MagicMock(returncode=0, stdout="Switched to branch 'main'", stderr="")
        with patch("subprocess.run", return_value=mock_ok):
            resp = client.post(
                "/api/repo/checkout/main",
                headers={"X-API-Key": TEST_KEY},
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_git_failure_returns_ok_false(self, client):
        mock_fail = MagicMock(returncode=128, stdout="", stderr="branch not found")
        with patch("subprocess.run", return_value=mock_fail):
            resp = client.post(
                "/api/repo/checkout/nonexistent-branch",
                headers={"X-API-Key": TEST_KEY},
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is False


# ── GET / (dashboard) ─────────────────────────────────────────────────────────

class TestDashboard:
    def test_returns_200(self, client):
        with patch("app.get_container_status", return_value="running"):
            resp = client.get("/")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        with patch("app.get_container_status", return_value="running"):
            resp = client.get("/")
        assert b"html" in resp.data.lower()
