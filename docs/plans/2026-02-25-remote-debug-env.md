# Remote Debug Environment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a self-contained remote dev environment on an existing Ubuntu 24 VM with debug-enabled Docker containers, a Flask orchestration API, and VS Code remote debugging for all .NET services and the Vue.js frontend.

**Architecture:** Docker Compose override pattern (`docker-compose-debug.yml` extends `docker-compose-local.yml`). ES/Kibana always-on from base compose; 4 .NET debug services + 1 Vite dev container managed by Flask. Each .NET debug image uses a hybrid 2-stage Dockerfile: SDK stage compiles Debug mode artifacts from saltminer source, prod image stage layers them on top with vsdbg installed.

**Tech Stack:** Python 3 + Flask, Docker Compose, .NET 8 SDK (debug builds), vsdbg (pipeTransport mode), Node.js 20 + Vite, pytest + unittest.mock

---

## Important Reference Information

**Existing compose files:**
- `docker-compose-local.yml` — full local stack (ES + Kibana + all app services)
- `docker-compose.yml` — app services only (prod)

**Actual container names** (explicit `container_name:` values in compose):
- `api` (compose service: `api`)
- `ui-api` (compose service: `ui-api`)
- `services` (compose service: `sm-services`)
- `jobmanager` (compose service: `jobmanager`)
- `smpgui` (compose service: `smpgui`)

**Compose project name:** `sm` (from `.env` COMPOSE_PROJECT_NAME)

**Network:** `saltminer`

**Production DLL paths inside containers:**
- api: `/usr/share/saltworks/saltminer-3.0.0/api/Saltworks.SaltMiner.DataApi.dll`
- ui-api: `/usr/share/saltworks/saltminer-3.0.0/ui-api/Saltworks.SaltMiner.Ui.Api.dll`
- sm-services: `/usr/share/saltworks/saltminer-3.0.0/servicemanager/Saltworks.SaltMiner.ServiceManager.dll`
- jobmanager: `/usr/share/saltworks/saltminer-3.0.0/jobmanager/Saltworks.SaltMiner.JobManager.dll`

**vsdbg approach:** pipeTransport (no listening port — VS Code communicates via `docker exec` stdin/stdout)

**VM paths:**
- saltminer-setup repo: `/opt/saltminer-dev/saltminer-setup`
- saltminer source repo: `/opt/saltminer-dev/saltminer`
- Flask API deployment: `/opt/saltminer-dev-api`

---

## Task 1: Create Directory Structure

**Files:**
- Create: `devops/dev-containers/.dockerfiles/` (directory)
- Create: `devops/dev-containers/orchestration-api/templates/` (directory)
- Create: `devops/dev-containers/vscode-templates/` (directory)
- Create: `docs/plans/` (directory, already done)

**Step 1: Create directory placeholders**

```bash
mkdir -p devops/dev-containers/.dockerfiles
mkdir -p devops/dev-containers/orchestration-api/templates
mkdir -p devops/dev-containers/vscode-templates
touch devops/dev-containers/.dockerfiles/.gitkeep
touch devops/dev-containers/vscode-templates/.gitkeep
```

**Step 2: Verify structure**

```bash
find devops/dev-containers -type d
```

Expected output:
```
devops/dev-containers
devops/dev-containers/.dockerfiles
devops/dev-containers/orchestration-api
devops/dev-containers/orchestration-api/templates
devops/dev-containers/vscode-templates
```

**Step 3: Commit**

```bash
git add devops/
git commit -m "chore: scaffold devops/dev-containers directory structure"
```

---

## Task 2: Dockerfile.debug.api

**Files:**
- Create: `devops/dev-containers/.dockerfiles/Dockerfile.debug.api`

**Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile.debug.api
# Hybrid debug image: compiles DataApi in Debug mode from source, layers onto prod base.
# Build context: /opt/saltminer-dev/saltminer (the saltminer source repo)
# Build command (handled by Flask API):
#   docker build -f devops/dev-containers/.dockerfiles/Dockerfile.debug.api \
#     --build-arg SM_API_IMAGE_VERSION=<version> \
#     -t saltminer-api-debug:latest \
#     /opt/saltminer-dev/saltminer

# ── Stage 1: Debug build ──────────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
# TODO: Verify .csproj path in the saltminer repository
RUN dotnet publish src/Saltworks.SaltMiner.DataApi/Saltworks.SaltMiner.DataApi.csproj \
    --configuration Debug \
    --output /app/debug \
    --no-self-contained

# ── Stage 2: Layer onto production base ───────────────────────────────────────
ARG SM_API_IMAGE_VERSION=latest
FROM docker.io/saltworks/saltminer:${SM_API_IMAGE_VERSION}
WORKDIR /usr/share/saltworks/saltminer-3.0.0/api

# Replace prod DLLs/PDBs with Debug build artifacts
COPY --from=build /app/debug/ .

# Install vsdbg (requires curl and bash in base image; both present per healthcheck usage)
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip bash \
 && curl -sSL https://aka.ms/getvsdbgsh | bash /dev/stdin -v latest -l /vsdbg \
 && rm -rf /var/lib/apt/lists/*

ENV ASPNETCORE_ENVIRONMENT=Development
ENV DOTNET_ENABLE_DIAGNOSTICS=1
```

**Step 2: Verify syntax**

```bash
# Dry-run parse (does not build — saves time without Docker access)
docker buildx build --help > /dev/null && echo "docker available"
# If no Docker locally, just review the file visually for syntax errors
cat devops/dev-containers/.dockerfiles/Dockerfile.debug.api
```

**Step 3: Commit**

```bash
git add devops/dev-containers/.dockerfiles/Dockerfile.debug.api
git commit -m "feat: add hybrid debug Dockerfile for DataApi service"
```

---

## Task 3: Dockerfile.debug.ui-api

**Files:**
- Create: `devops/dev-containers/.dockerfiles/Dockerfile.debug.ui-api`

**Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile.debug.ui-api
# Hybrid debug image: compiles UiApi in Debug mode from source, layers onto prod base.
# Build context: /opt/saltminer-dev/saltminer

# ── Stage 1: Debug build ──────────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
# TODO: Verify .csproj path in the saltminer repository
RUN dotnet publish src/Saltworks.SaltMiner.Ui.Api/Saltworks.SaltMiner.Ui.Api.csproj \
    --configuration Debug \
    --output /app/debug \
    --no-self-contained

# ── Stage 2: Layer onto production base ───────────────────────────────────────
ARG SM_UI_API_IMAGE_VERSION=latest
FROM docker.io/saltworks/saltminer:${SM_UI_API_IMAGE_VERSION}
WORKDIR /usr/share/saltworks/saltminer-3.0.0/ui-api

COPY --from=build /app/debug/ .

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip bash \
 && curl -sSL https://aka.ms/getvsdbgsh | bash /dev/stdin -v latest -l /vsdbg \
 && rm -rf /var/lib/apt/lists/*

ENV ASPNETCORE_ENVIRONMENT=Development
ENV DOTNET_ENABLE_DIAGNOSTICS=1
```

**Step 2: Commit**

```bash
git add devops/dev-containers/.dockerfiles/Dockerfile.debug.ui-api
git commit -m "feat: add hybrid debug Dockerfile for UiApi service"
```

---

## Task 4: Dockerfile.debug.sm-services

**Files:**
- Create: `devops/dev-containers/.dockerfiles/Dockerfile.debug.sm-services`

Note: `sm-services` container runs the ServiceManager DLL, which in turn spawns additional .NET processes. This Dockerfile installs vsdbg for the main ServiceManager process; spawned child processes can be attached separately in the same way.

**Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile.debug.sm-services
# Hybrid debug image: compiles ServiceManager in Debug mode, layers onto prod base.
# Build context: /opt/saltminer-dev/saltminer
# Note: ServiceManager spawns additional .NET processes. Each can be attached
# independently via "docker exec services /vsdbg/vsdbg ..."

# ── Stage 1: Debug build ──────────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
# TODO: Verify .csproj path in the saltminer repository
RUN dotnet publish src/Saltworks.SaltMiner.ServiceManager/Saltworks.SaltMiner.ServiceManager.csproj \
    --configuration Debug \
    --output /app/debug \
    --no-self-contained

# ── Stage 2: Layer onto production base ───────────────────────────────────────
ARG SM_SERVICES_IMAGE_VERSION=latest
FROM docker.io/saltworks/saltminer:${SM_SERVICES_IMAGE_VERSION}
WORKDIR /usr/share/saltworks/saltminer-3.0.0/servicemanager

COPY --from=build /app/debug/ .

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip bash \
 && curl -sSL https://aka.ms/getvsdbg | bash /dev/stdin -u vsdbg -l /vsdbg \
 && rm -rf /var/lib/apt/lists/*

ENV ASPNETCORE_ENVIRONMENT=Development
ENV DOTNET_ENABLE_DIAGNOSTICS=1
```

**Step 2: Commit**

```bash
git add devops/dev-containers/.dockerfiles/Dockerfile.debug.sm-services
git commit -m "feat: add hybrid debug Dockerfile for ServiceManager"
```

---

## Task 5: Dockerfile.debug.jobmanager

**Files:**
- Create: `devops/dev-containers/.dockerfiles/Dockerfile.debug.jobmanager`

**Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile.debug.jobmanager
# Hybrid debug image: compiles JobManager in Debug mode, layers onto prod base.
# Build context: /opt/saltminer-dev/saltminer

# ── Stage 1: Debug build ──────────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
# TODO: Verify .csproj path in the saltminer repository
RUN dotnet publish src/Saltworks.SaltMiner.JobManager/Saltworks.SaltMiner.JobManager.csproj \
    --configuration Debug \
    --output /app/debug \
    --no-self-contained

# ── Stage 2: Layer onto production base ───────────────────────────────────────
ARG SM_JOBMANAGER_IMAGE_VERSION=latest
FROM docker.io/saltworks/saltminer:${SM_JOBMANAGER_IMAGE_VERSION}
WORKDIR /usr/share/saltworks/saltminer-3.0.0/jobmanager

COPY --from=build /app/debug/ .

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip bash \
 && curl -sSL https://aka.ms/getvsdbg | bash /dev/stdin -u vsdbg -l /vsdbg \
 && rm -rf /var/lib/apt/lists/*

ENV ASPNETCORE_ENVIRONMENT=Development
ENV DOTNET_ENABLE_DIAGNOSTICS=1
```

**Step 2: Commit**

```bash
git add devops/dev-containers/.dockerfiles/Dockerfile.debug.jobmanager
git commit -m "feat: add hybrid debug Dockerfile for JobManager"
```

---

## Task 6: Dockerfile.debug.ui (Vite Dev Server)

**Files:**
- Create: `devops/dev-containers/.dockerfiles/Dockerfile.debug.ui`

This container replaces the `smpgui` init container. Source is bind-mounted at runtime so HMR picks up live edits. npm install runs on every container start (ensuring deps are always fresh; acceptable for a dev env).

**Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile.debug.ui
# Vite dev server for the SaltMiner Vue.js frontend.
# Source is bind-mounted at runtime — no COPY needed.
# Build context: /opt/saltminer-dev/saltminer (for .dockerignore context only)
# The actual source is supplied via bind mount in docker-compose-debug.yml.

FROM node:20-alpine

# Install bash for scripts that require it
RUN apk add --no-cache bash

WORKDIR /app

# Source directory is bind-mounted at runtime
# npm install runs on container start to ensure deps match current source
EXPOSE 5173
# Chrome DevTools Protocol port (for VS Code TypeScript/Vue debugging)
EXPOSE 9229

CMD ["sh", "-c", "npm install && npm run dev -- --host 0.0.0.0"]
```

**Step 2: Commit**

```bash
git add devops/dev-containers/.dockerfiles/Dockerfile.debug.ui
git commit -m "feat: add Vite dev server Dockerfile for Vue.js frontend"
```

---

## Task 7: docker-compose-debug.yml

**Files:**
- Create: `devops/dev-containers/docker-compose-debug.yml`

This file is used as an override on top of `docker-compose-local.yml`. Docker Compose merges volumes, environment variables, and ports. Only the differences from the base are declared here.

**Step 1: Write the compose override**

```yaml
# docker-compose-debug.yml
# Debug environment override — extends docker-compose-local.yml.
#
# Usage (run from /opt/saltminer-dev/saltminer-setup):
#   docker compose \
#     -f docker-compose-local.yml \
#     -f devops/dev-containers/docker-compose-debug.yml \
#     up -d
#
# Or use the Flask orchestration API at http://localhost:8080
#
# ES/Kibana are NOT touched — they run from docker-compose-local.yml unchanged.
# The 4 .NET services and smpgui are replaced with debug variants.

services:
  api:
    image: saltminer-api-debug:latest
    # container_name stays "api" (inherited) — required for vsdbg docker exec
    volumes:
      # Bind-mount source for vsdbg symbol resolution (read-only)
      - /opt/saltminer-dev/saltminer:/src:ro
    environment:
      - ASPNETCORE_ENVIRONMENT=Development
      - DOTNET_ENABLE_DIAGNOSTICS=1

  ui-api:
    image: saltminer-ui-api-debug:latest
    # container_name stays "ui-api" (inherited)
    volumes:
      - /opt/saltminer-dev/saltminer:/src:ro
    environment:
      - ASPNETCORE_ENVIRONMENT=Development
      - DOTNET_ENABLE_DIAGNOSTICS=1

  sm-services:
    image: saltminer-sm-services-debug:latest
    # container_name stays "services" (inherited)
    volumes:
      - /opt/saltminer-dev/saltminer:/src:ro
    environment:
      - ASPNETCORE_ENVIRONMENT=Development
      - DOTNET_ENABLE_DIAGNOSTICS=1

  jobmanager:
    image: saltminer-jobmanager-debug:latest
    # container_name stays "jobmanager" (inherited)
    volumes:
      - /opt/saltminer-dev/saltminer:/src:ro
    environment:
      - ASPNETCORE_ENVIRONMENT=Development
      - DOTNET_ENABLE_DIAGNOSTICS=1

  # Replace the smpgui static-asset init container with a Vite dev server.
  # TODO: Verify the path to the Vue.js source in the saltminer repo.
  smpgui:
    image: node:20-alpine
    container_name: smpgui
    working_dir: /app
    volumes:
      # Bind-mount Vue.js source so Vite HMR picks up live edits
      # TODO: Verify this path matches the Vue.js project root in saltminer
      - /opt/saltminer-dev/saltminer/src/SaltMiner.Ui:/app
    ports:
      - "5173:5173"
      - "9229:9229"
    environment:
      # Force polling-based file watch (required in Docker bind mounts on some hosts)
      - CHOKIDAR_USEPOLLING=true
      - VITE_DEV_SERVER_PORT=5173
    entrypoint: []
    command: sh -c "npm install && npm run dev -- --host 0.0.0.0"
    restart: "no"
    depends_on: []
    networks:
      - ${CONTAINER_NETWORK}
```

**Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('devops/dev-containers/docker-compose-debug.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

**Step 3: Commit**

```bash
git add devops/dev-containers/docker-compose-debug.yml
git commit -m "feat: add docker-compose-debug.yml override for debug services"
```

---

## Task 8: Flask API — Write Failing Tests

**Files:**
- Create: `devops/dev-containers/orchestration-api/tests/__init__.py`
- Create: `devops/dev-containers/orchestration-api/tests/test_app.py`

**Step 1: Write the tests (they will fail — app.py doesn't exist yet)**

```python
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
```

**Step 2: Run tests — verify they fail with ImportError**

```bash
cd devops/dev-containers/orchestration-api
pip install flask pytest --quiet
python -m pytest tests/test_app.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app'`

**Step 3: Commit failing tests**

```bash
git add devops/dev-containers/orchestration-api/tests/
git commit -m "test: add failing tests for Flask orchestration API"
```

---

## Task 9: Flask config.py

**Files:**
- Create: `devops/dev-containers/orchestration-api/config.py`
- Create: `devops/dev-containers/orchestration-api/.env.example`

**Step 1: Write config.py**

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# ── VM paths ──────────────────────────────────────────────────────────────────
SETUP_REPO = os.getenv("SETUP_REPO", "/opt/saltminer-dev/saltminer-setup")
SALTMINER_REPO = os.getenv("SALTMINER_REPO", "/opt/saltminer-dev/saltminer")

# ── Auth ──────────────────────────────────────────────────────────────────────
API_KEY = os.getenv("API_KEY", "changeme")

# ── Docker Compose files ──────────────────────────────────────────────────────
BASE_COMPOSE = os.path.join(SETUP_REPO, "docker-compose-local.yml")
DEBUG_COMPOSE = os.path.join(SETUP_REPO, "devops/dev-containers/docker-compose-debug.yml")
COMPOSE_CMD = ["docker", "compose", "-f", BASE_COMPOSE, "-f", DEBUG_COMPOSE]

# ── Service definitions ───────────────────────────────────────────────────────
# compose service name → actual Docker container name
# (container_name is explicitly set in docker-compose-local.yml)
SERVICE_CONTAINER_MAP = {
    "api": "api",
    "ui-api": "ui-api",
    "sm-services": "services",
    "jobmanager": "jobmanager",
    "smpgui": "smpgui",
}

ALL_DEBUG_SERVICES = list(SERVICE_CONTAINER_MAP.keys())

# Debug image names (built locally by this API)
DEBUG_IMAGE_MAP = {
    "api": "saltminer-api-debug:latest",
    "ui-api": "saltminer-ui-api-debug:latest",
    "sm-services": "saltminer-sm-services-debug:latest",
    "jobmanager": "saltminer-jobmanager-debug:latest",
    "smpgui": "node:20-alpine",  # no custom build needed
}

# Dockerfile paths for each buildable service
DOCKERFILE_MAP = {
    "api": os.path.join(SETUP_REPO, "devops/dev-containers/.dockerfiles/Dockerfile.debug.api"),
    "ui-api": os.path.join(SETUP_REPO, "devops/dev-containers/.dockerfiles/Dockerfile.debug.ui-api"),
    "sm-services": os.path.join(SETUP_REPO, "devops/dev-containers/.dockerfiles/Dockerfile.debug.sm-services"),
    "jobmanager": os.path.join(SETUP_REPO, "devops/dev-containers/.dockerfiles/Dockerfile.debug.jobmanager"),
    # smpgui uses node:20-alpine directly — no custom Dockerfile to build
}

# Version build-args for each service's base image
# These should match the versions in .env
VERSION_ARG_MAP = {
    "api": ("SM_API_IMAGE_VERSION", os.getenv("SM_API_IMAGE_VERSION", "latest")),
    "ui-api": ("SM_UI_API_IMAGE_VERSION", os.getenv("SM_UI_API_IMAGE_VERSION", "latest")),
    "sm-services": ("SM_SERVICES_IMAGE_VERSION", os.getenv("SM_SERVICES_IMAGE_VERSION", "latest")),
    "jobmanager": ("SM_JOBMANAGER_IMAGE_VERSION", os.getenv("SM_JOBMANAGER_IMAGE_VERSION", "latest")),
}
```

**Step 2: Write .env.example**

```ini
# .env.example — copy to .env and fill in values

# API authentication key (required for all POST endpoints)
API_KEY=changeme

# VM paths to the cloned repositories
SETUP_REPO=/opt/saltminer-dev/saltminer-setup
SALTMINER_REPO=/opt/saltminer-dev/saltminer

# SaltMiner image versions (copy from saltminer-setup/.env)
SM_API_IMAGE_VERSION=api-3.2.0.20251002-141405
SM_UI_API_IMAGE_VERSION=ui-api-3.2.0.20251002-191653
SM_SERVICES_IMAGE_VERSION=services-3.2.0.20251008-140253
SM_JOBMANAGER_IMAGE_VERSION=jobmanager-3.2.0.20251002-191541
```

**Step 3: Commit**

```bash
git add devops/dev-containers/orchestration-api/config.py \
        devops/dev-containers/orchestration-api/.env.example
git commit -m "feat: add Flask API config module and .env.example"
```

---

## Task 10: Flask app.py (make tests pass)

**Files:**
- Create: `devops/dev-containers/orchestration-api/app.py`

**Step 1: Write app.py**

```python
# app.py
import subprocess

from flask import Flask, abort, jsonify, render_template, request

from config import (
    ALL_DEBUG_SERVICES,
    API_KEY,
    COMPOSE_CMD,
    DEBUG_IMAGE_MAP,
    DOCKERFILE_MAP,
    SALTMINER_REPO,
    SERVICE_CONTAINER_MAP,
    VERSION_ARG_MAP,
)

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def require_api_key():
    if request.headers.get("X-API-Key") != API_KEY:
        abort(401, description="Invalid or missing X-API-Key header")


def run_compose(args, timeout=300):
    cmd = COMPOSE_CMD + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def get_container_status(container_name):
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "not found"


def build_service_image(name):
    """Build the debug Docker image for a .NET service. Returns subprocess.CompletedProcess."""
    dockerfile = DOCKERFILE_MAP[name]
    image = DEBUG_IMAGE_MAP[name]
    arg_name, arg_value = VERSION_ARG_MAP[name]
    return subprocess.run(
        [
            "docker", "build",
            "-f", dockerfile,
            "-t", image,
            "--build-arg", f"{arg_name}={arg_value}",
            SALTMINER_REPO,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    services = [
        {
            "name": name,
            "container": SERVICE_CONTAINER_MAP[name],
            "status": get_container_status(SERVICE_CONTAINER_MAP[name]),
        }
        for name in ALL_DEBUG_SERVICES
    ]
    return render_template("index.html", services=services)


@app.route("/api/status")
def status():
    return jsonify({
        "status": {
            name: get_container_status(SERVICE_CONTAINER_MAP[name])
            for name in ALL_DEBUG_SERVICES
        }
    })


@app.route("/api/services")
def list_services():
    return jsonify([
        {
            "name": name,
            "container": SERVICE_CONTAINER_MAP[name],
            "status": get_container_status(SERVICE_CONTAINER_MAP[name]),
        }
        for name in ALL_DEBUG_SERVICES
    ])


@app.route("/api/services/<name>/start", methods=["POST"])
def start_service(name):
    require_api_key()
    if name not in ALL_DEBUG_SERVICES:
        abort(404, description=f"Unknown service: {name}")
    result = run_compose(["up", "-d", name])
    return jsonify({"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr})


@app.route("/api/services/<name>/stop", methods=["POST"])
def stop_service(name):
    require_api_key()
    if name not in ALL_DEBUG_SERVICES:
        abort(404, description=f"Unknown service: {name}")
    result = run_compose(["stop", name])
    return jsonify({"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr})


@app.route("/api/services/<name>/rebuild", methods=["POST"])
def rebuild_service(name):
    require_api_key()
    if name not in ALL_DEBUG_SERVICES:
        abort(404, description=f"Unknown service: {name}")
    if name not in DOCKERFILE_MAP:
        # smpgui uses stock node image — just restart it
        result = run_compose(["up", "-d", "--force-recreate", name])
        return jsonify({"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr})
    build = build_service_image(name)
    if build.returncode != 0:
        return jsonify({"ok": False, "stage": "build", "error": build.stderr}), 500
    run_compose(["stop", name])
    start = run_compose(["up", "-d", "--no-build", name])
    return jsonify({
        "ok": start.returncode == 0,
        "build_output": build.stdout,
        "output": start.stdout,
        "error": start.stderr,
    })


@app.route("/api/services/rebuild-all", methods=["POST"])
def rebuild_all():
    require_api_key()
    builds = {}
    for name in DOCKERFILE_MAP:
        result = build_service_image(name)
        builds[name] = {"built": result.returncode == 0, "error": result.stderr if result.returncode != 0 else ""}
    up = run_compose(["up", "-d", "--no-build"] + ALL_DEBUG_SERVICES)
    return jsonify({"builds": builds, "up": {"ok": up.returncode == 0, "output": up.stdout}})


@app.route("/api/services/<name>/logs")
def get_logs(name):
    if name not in ALL_DEBUG_SERVICES:
        abort(404, description=f"Unknown service: {name}")
    lines = request.args.get("lines", "100")
    result = run_compose(["logs", "--tail", lines, name])
    return jsonify({"logs": result.stdout, "error": result.stderr})


@app.route("/api/ui/restart", methods=["POST"])
def restart_ui():
    require_api_key()
    run_compose(["stop", "smpgui"])
    result = run_compose(["up", "-d", "smpgui"])
    return jsonify({"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr})


@app.route("/api/repo/checkout/<branch>", methods=["POST"])
def checkout_branch(branch):
    require_api_key()
    result = subprocess.run(
        ["git", "-C", SALTMINER_REPO, "checkout", branch],
        capture_output=True,
        text=True,
    )
    return jsonify({"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
```

**Step 2: Run tests — all should pass**

```bash
cd devops/dev-containers/orchestration-api
python -m pytest tests/test_app.py -v
```

Expected: all tests pass (`PASSED` for each)

**Step 3: Commit**

```bash
git add devops/dev-containers/orchestration-api/app.py
git commit -m "feat: implement Flask orchestration API (all tests passing)"
```

---

## Task 11: HTML Dashboard (templates/index.html)

**Files:**
- Create: `devops/dev-containers/orchestration-api/templates/index.html`

**Step 1: Write the dashboard**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SaltMiner Dev</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }
    h1 { color: #7dd3fc; margin-bottom: 0.25rem; }
    .subtitle { color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }
    .api-key-row { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 1.5rem; }
    .api-key-row label { color: #94a3b8; font-size: 0.85rem; }
    .api-key-row input { background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
                         padding: 0.4rem 0.7rem; border-radius: 4px; width: 260px; font-family: monospace; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; }
    th { text-align: left; padding: 0.6rem 1rem; background: #1e293b; color: #94a3b8;
         font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    td { padding: 0.7rem 1rem; border-bottom: 1px solid #1e293b; }
    .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px;
             font-size: 0.75rem; font-weight: 600; }
    .running  { background: #14532d; color: #86efac; }
    .stopped  { background: #450a0a; color: #fca5a5; }
    .not-found { background: #1e293b; color: #94a3b8; }
    .other    { background: #431407; color: #fed7aa; }
    .actions { display: flex; gap: 0.4rem; }
    button { padding: 0.3rem 0.7rem; border: none; border-radius: 4px; cursor: pointer;
             font-size: 0.8rem; font-weight: 500; transition: opacity 0.15s; }
    button:hover { opacity: 0.85; }
    .btn-start   { background: #15803d; color: #fff; }
    .btn-stop    { background: #b91c1c; color: #fff; }
    .btn-rebuild { background: #1d4ed8; color: #fff; }
    .global-actions { display: flex; gap: 0.75rem; margin-bottom: 2rem; }
    .btn-global  { padding: 0.5rem 1.2rem; border: none; border-radius: 6px; cursor: pointer;
                   font-size: 0.9rem; font-weight: 600; transition: opacity 0.15s; }
    .btn-global:hover { opacity: 0.85; }
    .btn-rebuild-all { background: #7c3aed; color: #fff; }
    .btn-ui-restart  { background: #0e7490; color: #fff; }
    .checkout-row { display: flex; gap: 0.5rem; align-items: center; margin-top: 1.5rem; }
    .checkout-row input { background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
                          padding: 0.4rem 0.7rem; border-radius: 4px; width: 200px; }
    .checkout-row button { background: #0f766e; color: #fff; padding: 0.4rem 1rem;
                           border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
    #toast { position: fixed; bottom: 1.5rem; right: 1.5rem; padding: 0.75rem 1.25rem;
             background: #0f172a; border: 1px solid #334155; border-radius: 8px;
             color: #e2e8f0; font-size: 0.85rem; opacity: 0; transition: opacity 0.3s;
             max-width: 340px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>SaltMiner Dev Environment</h1>
  <p class="subtitle">Orchestration API — manages debug containers on the remote VM</p>

  <div class="api-key-row">
    <label for="apiKey">API Key:</label>
    <input type="password" id="apiKey" placeholder="enter API key" autocomplete="off">
  </div>

  <div class="global-actions">
    <button class="btn-global btn-rebuild-all" onclick="rebuildAll()">⟳ Rebuild All</button>
    <button class="btn-global btn-ui-restart" onclick="restartUi()">↺ Restart UI (Vite)</button>
  </div>

  <table>
    <thead>
      <tr><th>Service</th><th>Container</th><th>Status</th><th>Actions</th></tr>
    </thead>
    <tbody id="serviceTable">
      {% for svc in services %}
      <tr id="row-{{ svc.name }}">
        <td>{{ svc.name }}</td>
        <td><code>{{ svc.container }}</code></td>
        <td><span class="badge {{ svc.status if svc.status in ['running','stopped'] else ('not-found' if svc.status == 'not found' else 'other') }}">{{ svc.status }}</span></td>
        <td>
          <div class="actions">
            <button class="btn-start"   onclick="callApi('POST','/api/services/{{ svc.name }}/start',   '{{ svc.name }} starting…')">Start</button>
            <button class="btn-stop"    onclick="callApi('POST','/api/services/{{ svc.name }}/stop',    '{{ svc.name }} stopping…')">Stop</button>
            <button class="btn-rebuild" onclick="callApi('POST','/api/services/{{ svc.name }}/rebuild', '{{ svc.name }} rebuilding… (may take a few minutes)')">Rebuild</button>
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="checkout-row">
    <label>Checkout branch:</label>
    <input type="text" id="branchInput" placeholder="e.g. main">
    <button onclick="checkoutBranch()">Checkout</button>
  </div>

  <div id="toast"></div>

  <script>
    function apiKey() { return document.getElementById('apiKey').value; }

    function toast(msg, durationMs = 4000) {
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.style.opacity = '1';
      clearTimeout(el._t);
      el._t = setTimeout(() => { el.style.opacity = '0'; }, durationMs);
    }

    async function callApi(method, path, pendingMsg) {
      toast(pendingMsg);
      try {
        const resp = await fetch(path, {
          method,
          headers: { 'X-API-Key': apiKey() },
        });
        const data = await resp.json();
        if (resp.status === 401) { toast('❌ Invalid API key'); return; }
        toast(data.ok !== false ? '✓ ' + path + ' — OK' : '✗ Error: ' + (data.error || 'unknown'), 6000);
      } catch (e) {
        toast('❌ Network error: ' + e.message);
      }
    }

    async function rebuildAll() {
      toast('Rebuilding all services… this may take several minutes');
      try {
        const resp = await fetch('/api/services/rebuild-all', {
          method: 'POST',
          headers: { 'X-API-Key': apiKey() },
        });
        const data = await resp.json();
        const failed = Object.entries(data.builds || {}).filter(([, v]) => !v.built).map(([k]) => k);
        if (failed.length) toast('✗ Build failed for: ' + failed.join(', '), 8000);
        else toast('✓ All services rebuilt and started', 5000);
      } catch (e) { toast('❌ ' + e.message); }
    }

    async function restartUi() {
      toast('Restarting Vite dev server…');
      try {
        const resp = await fetch('/api/ui/restart', {
          method: 'POST',
          headers: { 'X-API-Key': apiKey() },
        });
        const data = await resp.json();
        toast(data.ok ? '✓ UI restarted' : '✗ Error: ' + data.error, 5000);
      } catch (e) { toast('❌ ' + e.message); }
    }

    async function checkoutBranch() {
      const branch = document.getElementById('branchInput').value.trim();
      if (!branch) { toast('Enter a branch name'); return; }
      toast(`Checking out ${branch}…`);
      try {
        const resp = await fetch(`/api/repo/checkout/${encodeURIComponent(branch)}`, {
          method: 'POST',
          headers: { 'X-API-Key': apiKey() },
        });
        const data = await resp.json();
        toast(data.ok ? `✓ Switched to ${branch}` : '✗ ' + (data.error || 'checkout failed'), 6000);
      } catch (e) { toast('❌ ' + e.message); }
    }
  </script>
</body>
</html>
```

**Step 2: Test dashboard renders**

```bash
cd devops/dev-containers/orchestration-api
python -c "
from unittest.mock import patch
import os, sys
os.environ['API_KEY'] = 'test'
os.environ['SETUP_REPO'] = '/fake'
os.environ['SALTMINER_REPO'] = '/fake'
from app import app
with app.test_client() as c:
    with patch('app.get_container_status', return_value='running'):
        r = c.get('/')
    assert r.status_code == 200
    assert b'SaltMiner Dev' in r.data
    print('Dashboard OK')
"
```

Expected: `Dashboard OK`

**Step 3: Run full test suite**

```bash
python -m pytest tests/test_app.py -v
```

Expected: all tests pass

**Step 4: Commit**

```bash
git add devops/dev-containers/orchestration-api/templates/
git commit -m "feat: add HTML dashboard for Flask orchestration API"
```

---

## Task 12: requirements.txt + systemd unit

**Files:**
- Create: `devops/dev-containers/orchestration-api/requirements.txt`
- Create: `devops/dev-containers/orchestration-api/saltminer-dev-api.service`

**Step 1: Write requirements.txt**

```
flask>=3.0,<4.0
python-dotenv>=1.0,<2.0
```

Test-only (not deployed):
```
# For local development / testing:
# pip install pytest
```

> Note: Keep this as comments in the file, not separate requirements-test.txt, to stay simple.

**Actual requirements.txt content:**

```
flask>=3.0,<4.0
python-dotenv>=1.0,<2.0
```

**Step 2: Write saltminer-dev-api.service (systemd unit)**

```ini
[Unit]
Description=SaltMiner Dev Orchestration API
Documentation=https://github.com/saltworks/saltminer
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=<YOUR_VM_USER>
WorkingDirectory=/opt/saltminer-dev-api
EnvironmentFile=/opt/saltminer-dev-api/.env
ExecStart=/usr/bin/python3 /opt/saltminer-dev-api/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> The `<YOUR_VM_USER>` placeholder must be replaced with the actual VM username during setup.

**Step 3: Commit**

```bash
git add devops/dev-containers/orchestration-api/requirements.txt \
        devops/dev-containers/orchestration-api/saltminer-dev-api.service
git commit -m "feat: add requirements.txt and systemd unit for orchestration API"
```

---

## Task 13: saltminer.http (VS Code / httpyac request file)

**Files:**
- Create: `devops/dev-containers/orchestration-api/saltminer.http`

**Step 1: Write the request file**

```http
# saltminer.http
# VS Code REST Client / httpyac compatible.
# Install REST Client extension: ms-vscode.rest-client
# Or httpyac: anweber.vscode-httpyac
#
# Usage:
#   1. Open this file in VS Code
#   2. Set the variables below
#   3. Click "Send Request" above any ### block

@baseUrl = http://localhost:8080
@apiKey = changeme

# ── Read-only ─────────────────────────────────────────────────────────────────

### Overall stack status
GET {{baseUrl}}/api/status

###

### List all services with status
GET {{baseUrl}}/api/services

###

### Get api logs (last 100 lines)
GET {{baseUrl}}/api/services/api/logs?lines=100

###

### Get ui-api logs
GET {{baseUrl}}/api/services/ui-api/logs?lines=100

###

### Get sm-services logs
GET {{baseUrl}}/api/services/sm-services/logs?lines=100

###

### Get jobmanager logs
GET {{baseUrl}}/api/services/jobmanager/logs?lines=100

###

### Get smpgui (Vite) logs
GET {{baseUrl}}/api/services/smpgui/logs?lines=200

# ── Service control ───────────────────────────────────────────────────────────

### Start api
POST {{baseUrl}}/api/services/api/start
X-API-Key: {{apiKey}}

###

### Stop api
POST {{baseUrl}}/api/services/api/stop
X-API-Key: {{apiKey}}

###

### Rebuild api (builds debug image from source, then restarts)
POST {{baseUrl}}/api/services/api/rebuild
X-API-Key: {{apiKey}}

###

### Start ui-api
POST {{baseUrl}}/api/services/ui-api/start
X-API-Key: {{apiKey}}

###

### Stop ui-api
POST {{baseUrl}}/api/services/ui-api/stop
X-API-Key: {{apiKey}}

###

### Rebuild ui-api
POST {{baseUrl}}/api/services/ui-api/rebuild
X-API-Key: {{apiKey}}

###

### Start sm-services
POST {{baseUrl}}/api/services/sm-services/start
X-API-Key: {{apiKey}}

###

### Stop sm-services
POST {{baseUrl}}/api/services/sm-services/stop
X-API-Key: {{apiKey}}

###

### Rebuild sm-services
POST {{baseUrl}}/api/services/sm-services/rebuild
X-API-Key: {{apiKey}}

###

### Start jobmanager
POST {{baseUrl}}/api/services/jobmanager/start
X-API-Key: {{apiKey}}

###

### Stop jobmanager
POST {{baseUrl}}/api/services/jobmanager/stop
X-API-Key: {{apiKey}}

###

### Rebuild jobmanager
POST {{baseUrl}}/api/services/jobmanager/rebuild
X-API-Key: {{apiKey}}

###

### Rebuild ALL services (builds all debug images, then starts everything)
# ⚠ This may take 5-10 minutes on first run
POST {{baseUrl}}/api/services/rebuild-all
X-API-Key: {{apiKey}}

###

### Restart UI (Vite dev server — stop + npm install + npm run dev)
POST {{baseUrl}}/api/ui/restart
X-API-Key: {{apiKey}}

# ── Repository ────────────────────────────────────────────────────────────────

### Checkout a branch on the saltminer source repo
# Branch name is in the URL path. After checkout, rebuild to pick up changes.
POST {{baseUrl}}/api/repo/checkout/main
X-API-Key: {{apiKey}}
```

**Step 2: Commit**

```bash
git add devops/dev-containers/orchestration-api/saltminer.http
git commit -m "feat: add saltminer.http request file for VS Code REST Client / httpyac"
```

---

## Task 14: VS Code launch.json.template

**Files:**
- Create: `devops/dev-containers/vscode-templates/launch.json.template`

**Step 1: Write the template**

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Attach: api",
      "type": "coreclr",
      "request": "attach",
      "processName": "dotnet",
      "pipeTransport": {
        "pipeProgram": "docker",
        "pipeArgs": ["exec", "-i", "api"],
        "debuggerPath": "/vsdbg/vsdbg",
        "pipeCwd": "${workspaceRoot}"
      },
      "sourceFileMap": {
        "/src": "${workspaceRoot}"
      }
    },
    {
      "name": "Attach: ui-api",
      "type": "coreclr",
      "request": "attach",
      "processName": "dotnet",
      "pipeTransport": {
        "pipeProgram": "docker",
        "pipeArgs": ["exec", "-i", "ui-api"],
        "debuggerPath": "/vsdbg/vsdbg",
        "pipeCwd": "${workspaceRoot}"
      },
      "sourceFileMap": {
        "/src": "${workspaceRoot}"
      }
    },
    {
      "name": "Attach: sm-services",
      "type": "coreclr",
      "request": "attach",
      "processName": "dotnet",
      "pipeTransport": {
        "pipeProgram": "docker",
        "pipeArgs": ["exec", "-i", "services"],
        "debuggerPath": "/vsdbg/vsdbg",
        "pipeCwd": "${workspaceRoot}"
      },
      "sourceFileMap": {
        "/src": "${workspaceRoot}"
      }
    },
    {
      "name": "Attach: jobmanager",
      "type": "coreclr",
      "request": "attach",
      "processName": "dotnet",
      "pipeTransport": {
        "pipeProgram": "docker",
        "pipeArgs": ["exec", "-i", "jobmanager"],
        "debuggerPath": "/vsdbg/vsdbg",
        "pipeCwd": "${workspaceRoot}"
      },
      "sourceFileMap": {
        "/src": "${workspaceRoot}"
      }
    },
    {
      "name": "Debug: UI (Chrome / Edge)",
      "type": "chrome",
      "request": "launch",
      "url": "http://localhost:5173",
      "webRoot": "${workspaceRoot}/src/SaltMiner.Ui",
      "sourceMapPathOverrides": {
        "/app/*": "${workspaceRoot}/src/SaltMiner.Ui/*"
      }
    }
  ]
}
```

**NOTE:** The `docker exec` container names (`api`, `ui-api`, `services`, `jobmanager`) are the literal `container_name` values from `docker-compose-local.yml`. If these change, update `pipeArgs` to match.

**Step 2: Commit**

```bash
git add devops/dev-containers/vscode-templates/launch.json.template
git commit -m "feat: add VS Code launch.json template with .NET and Vue debug configs"
```

---

## Task 15: VS Code tasks.json.template and settings.json.template

**Files:**
- Create: `devops/dev-containers/vscode-templates/tasks.json.template`
- Create: `devops/dev-containers/vscode-templates/settings.json.template`

**Step 1: Write tasks.json.template**

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "SM: Rebuild api",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/services/api/rebuild | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Rebuild ui-api",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/services/ui-api/rebuild | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Rebuild sm-services",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/services/sm-services/rebuild | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Rebuild jobmanager",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/services/jobmanager/rebuild | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Rebuild ALL services",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/services/rebuild-all | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Restart UI (Vite)",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/ui/restart | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Service status",
      "type": "shell",
      "command": "curl -s http://localhost:8080/api/services | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    },
    {
      "label": "SM: Checkout branch",
      "type": "shell",
      "command": "curl -s -X POST -H 'X-API-Key: ${input:apiKey}' http://localhost:8080/api/repo/checkout/${input:branch} | python3 -m json.tool",
      "group": "none",
      "presentation": { "reveal": "always", "panel": "shared" }
    }
  ],
  "inputs": [
    {
      "id": "apiKey",
      "type": "promptString",
      "description": "Flask API key",
      "password": true
    },
    {
      "id": "branch",
      "type": "promptString",
      "description": "Branch name to checkout"
    }
  ]
}
```

**Step 2: Write settings.json.template**

```json
{
  "remote.SSH.defaultForwardedPorts": [
    { "localPort": 8080, "remotePort": 8080, "name": "Flask Orchestration API" },
    { "localPort": 5173, "remotePort": 5173, "name": "Vite Dev Server" }
  ],
  "remote.SSH.serverInstallPath": {
    "<YOUR_VM_HOST>": "/home/<YOUR_VM_USER>/.vscode-server"
  }
}
```

**Step 3: Commit**

```bash
git add devops/dev-containers/vscode-templates/tasks.json.template \
        devops/dev-containers/vscode-templates/settings.json.template
git commit -m "feat: add VS Code tasks.json and settings.json templates"
```

---

## Task 16: README.md (VM Setup Guide)

**Files:**
- Create: `devops/dev-containers/README.md`

**Step 1: Write the README**

```markdown
# SaltMiner Remote Debug Environment

Remote development environment on Ubuntu 24. VS Code connects via Remote-SSH, attaches debuggers to all .NET services, and runs the Vue.js frontend via Vite dev server with HMR.

## Prerequisites

- Ubuntu 24 VM (existing) with SSH access
- VS Code with extensions: **Remote - SSH**, **C# Dev Kit** (ms-dotnettools.csdevkit), **REST Client** (ms-vscode.rest-client)
- Docker 24+ and docker-compose-plugin installed on the VM
- .NET SDK 8.0 installed on the VM

## One-Time VM Setup

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

### 2. Install .NET SDK 8.0

```bash
wget https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb -O /tmp/packages-microsoft-prod.deb
sudo dpkg -i /tmp/packages-microsoft-prod.deb
sudo apt-get update
sudo apt-get install -y dotnet-sdk-8.0
```

### 3. Clone repositories

```bash
sudo mkdir -p /opt/saltminer-dev
sudo chown $USER /opt/saltminer-dev

git clone <saltminer-setup-repo-url> /opt/saltminer-dev/saltminer-setup
git clone https://github.com/saltworks/saltminer /opt/saltminer-dev/saltminer
```

### 4. Install vsdbg on VM host (for prototype validation)

```bash
curl -sSL https://aka.ms/getvsdbgsh | sudo bash /dev/stdin -v latest -l /vsdbg
```

### 5. Validate vsdbg-over-SSH (IMPORTANT — do this before containers)

Before wiring up containers, confirm VS Code → SSH → vsdbg works:

```bash
# On VM: create and run a test .NET app
mkdir /tmp/vsdbg-test && cd /tmp/vsdbg-test
dotnet new console
dotnet run &   # note the PID
```

In VS Code (connected via Remote-SSH), create `/tmp/vsdbg-test/.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [{
    "name": "Test vsdbg",
    "type": "coreclr",
    "request": "attach",
    "processId": "${command:pickProcess}"
  }]
}
```
Run "Test vsdbg" and confirm the debugger attaches to the dotnet process.

If successful, the `launch.json` template in `vscode-templates/` is ready to use.
If not, troubleshoot SSH connectivity and vsdbg path before proceeding.

### 6. Configure .csproj paths in Dockerfiles

The Dockerfiles contain `# TODO: Verify .csproj path` comments. Open each Dockerfile and replace the placeholder paths with the correct paths from the saltminer repo:

- `Dockerfile.debug.api` → find `Saltworks.SaltMiner.DataApi.csproj`
- `Dockerfile.debug.ui-api` → find `Saltworks.SaltMiner.Ui.Api.csproj`
- `Dockerfile.debug.sm-services` → find `Saltworks.SaltMiner.ServiceManager.csproj`
- `Dockerfile.debug.jobmanager` → find `Saltworks.SaltMiner.JobManager.csproj`
- `docker-compose-debug.yml` → find the Vue.js project root (contains `package.json`)

```bash
# Quick search in the saltminer repo
find /opt/saltminer-dev/saltminer -name "*.csproj" | sort
find /opt/saltminer-dev/saltminer -name "package.json" -not -path "*/node_modules/*"
```

### 7. Deploy Flask orchestration API

```bash
cp -r /opt/saltminer-dev/saltminer-setup/devops/dev-containers/orchestration-api /opt/saltminer-dev-api
cd /opt/saltminer-dev-api
pip3 install -r requirements.txt

# Create .env from example
cp .env.example .env
# Edit .env: set a strong API_KEY and verify image versions match saltminer-setup/.env
nano .env

# Install and start systemd service
# Edit saltminer-dev-api.service: replace <YOUR_VM_USER> with your username
sed -i "s/<YOUR_VM_USER>/$USER/" saltminer-dev-api.service
sudo cp saltminer-dev-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saltminer-dev-api

# Verify it started
sudo systemctl status saltminer-dev-api
curl http://localhost:8080/api/status
```

### 8. Start stable infrastructure (Elasticsearch + Kibana)

Follow the standard setup from the main `README.md` for initial ES/Kibana startup.

```bash
cd /opt/saltminer-dev/saltminer-setup
# Run only ES + Kibana from the local compose (they remain stable)
docker compose -f docker-compose-local.yml up setup es01 kibana -d
```

### 9. Build and start debug services

```bash
# Via curl (API key from your .env)
curl -X POST -H "X-API-Key: <your-key>" http://localhost:8080/api/services/rebuild-all

# Or open the dashboard in your browser (after SSH port forwarding)
# http://localhost:8080
```

First build takes 5–10 minutes (downloads SDK and prod base images).

### 10. Configure VS Code workspace

```bash
# On your workstation — add VM to SSH config
cat >> ~/.ssh/config << 'EOF'
Host saltminer-dev
  HostName <VM_IP_OR_HOSTNAME>
  User <YOUR_VM_USER>
  IdentityFile ~/.ssh/id_rsa
EOF
```

In VS Code:
1. Remote-SSH: Connect to Host → `saltminer-dev`
2. Open folder → `/opt/saltminer-dev/saltminer`
3. Copy VS Code templates:
   ```bash
   mkdir -p /opt/saltminer-dev/saltminer/.vscode
   cp /opt/saltminer-dev/saltminer-setup/devops/dev-containers/vscode-templates/launch.json.template \
      /opt/saltminer-dev/saltminer/.vscode/launch.json
   cp /opt/saltminer-dev/saltminer-setup/devops/dev-containers/vscode-templates/tasks.json.template \
      /opt/saltminer-dev/saltminer/.vscode/tasks.json
   cp /opt/saltminer-dev/saltminer-setup/devops/dev-containers/vscode-templates/settings.json.template \
      /opt/saltminer-dev/saltminer/.vscode/settings.json
   # Edit settings.json: replace <YOUR_VM_HOST> and <YOUR_VM_USER>
   ```
4. Install recommended extensions (C# Dev Kit, REST Client) when prompted.

## Daily Usage

### Attach .NET debugger

1. Ensure the service container is running (`GET /api/services`)
2. In VS Code Run & Debug → select "Attach: api" (or other service)
3. Set breakpoints in source files
4. Trigger an API call — breakpoint should hit

### Debug Vue.js frontend

1. Ensure `smpgui` (Vite) is running — navigate to `http://localhost:5173`
2. In VS Code Run & Debug → "Debug: UI (Chrome / Edge)"
3. Set breakpoints in `.vue` or `.ts` files

### Rebuild after code changes

```bash
# Via tasks (Ctrl+Shift+P → "Tasks: Run Task")
# Or via curl:
curl -X POST -H "X-API-Key: <key>" http://localhost:8080/api/services/api/rebuild

# Rebuild all:
curl -X POST -H "X-API-Key: <key>" http://localhost:8080/api/services/rebuild-all
```

### Switch branches

```bash
curl -X POST -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"branch":"feature/my-branch"}' \
  http://localhost:8080/api/repo/checkout
# Then rebuild affected services
```

## Troubleshooting

**Debugger can't attach:**
- Confirm container is running: `docker ps | grep api`
- Confirm vsdbg is installed: `docker exec api ls /vsdbg/vsdbg`
- Check that the debug image (not prod) is running: `docker inspect api | grep Image`

**Vite HMR not picking up changes:**
- `POST /api/ui/restart` to stop and restart the container
- Confirm `CHOKIDAR_USEPOLLING=true` is set in `docker-compose-debug.yml`

**Build fails with "project file not found":**
- Check `# TODO` comments in Dockerfiles and update `.csproj` paths

**Flask API not responding:**
- `sudo systemctl status saltminer-dev-api`
- `sudo journalctl -u saltminer-dev-api -n 50`
```

**Step 2: Commit**

```bash
git add devops/dev-containers/README.md
git commit -m "docs: add VM setup guide for remote debug environment"
```

---

## Task 17: Final Verification Commit

**Step 1: Verify all expected files exist**

```bash
find devops/dev-containers -type f | sort
```

Expected output (all 17 files):
```
devops/dev-containers/.dockerfiles/.gitkeep
devops/dev-containers/.dockerfiles/Dockerfile.debug.api
devops/dev-containers/.dockerfiles/Dockerfile.debug.jobmanager
devops/dev-containers/.dockerfiles/Dockerfile.debug.sm-services
devops/dev-containers/.dockerfiles/Dockerfile.debug.ui
devops/dev-containers/.dockerfiles/Dockerfile.debug.ui-api
devops/dev-containers/README.md
devops/dev-containers/docker-compose-debug.yml
devops/dev-containers/orchestration-api/.env.example
devops/dev-containers/orchestration-api/app.py
devops/dev-containers/orchestration-api/config.py
devops/dev-containers/orchestration-api/requirements.txt
devops/dev-containers/orchestration-api/saltminer-dev-api.service
devops/dev-containers/orchestration-api/saltminer.http
devops/dev-containers/orchestration-api/templates/index.html
devops/dev-containers/orchestration-api/tests/__init__.py
devops/dev-containers/orchestration-api/tests/test_app.py
devops/dev-containers/vscode-templates/launch.json.template
devops/dev-containers/vscode-templates/settings.json.template
devops/dev-containers/vscode-templates/tasks.json.template
```

**Step 2: Run the full test suite one final time**

```bash
cd devops/dev-containers/orchestration-api
pip install flask python-dotenv pytest --quiet
python -m pytest tests/test_app.py -v
```

Expected: all tests pass, zero failures

**Step 3: Verify YAML files are valid**

```bash
python3 -c "
import yaml
files = [
  'devops/dev-containers/docker-compose-debug.yml',
]
for f in files:
    yaml.safe_load(open(f))
    print(f'✓ {f}')
"
```

**Step 4: Final commit**

```bash
git add devops/ai-plans/remote-debug-env.md docs/plans/2026-02-25-remote-debug-env.md
git commit -m "docs: add design doc and implementation plan for remote debug environment"
```

---

## Post-Implementation: Verify on VM

These steps are performed on the Ubuntu VM, not in this repo:

1. `curl http://localhost:8080/api/status` — all 5 debug services listed
2. Open `http://localhost:8080` (SSH port-forwarded) — dashboard loads with service table
3. VS Code Remote-SSH → open `/opt/saltminer-dev/saltminer` workspace
4. Set breakpoint in DataApi, run "Attach: api" → breakpoint hits on a request
5. Navigate to `http://localhost:5173` → Vue.js UI loads
6. Set breakpoint in a `.vue` component, run "Debug: UI (Chrome / Edge)" → breakpoint hits
7. `POST /api/repo/checkout {"branch": "develop"}` → OK
8. `POST /api/services/api/rebuild` → rebuilds with develop branch code
