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
        # smpgui uses stock node image — just force-recreate
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
