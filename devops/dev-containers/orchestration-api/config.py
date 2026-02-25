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
