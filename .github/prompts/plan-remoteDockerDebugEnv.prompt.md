## Plan: Remote Docker Debug Environment for SaltMiner

**TL;DR:** Create a remote Ubuntu 24 dev environment with debug-enabled Docker containers. VS Code connects via Remote-SSH, attaches debuggers to .NET apps via vsdbg. A small orchestration API enables quick start/stop/rebuild cycles controllable by both humans and AI. Elasticsearch/Kibana remain stable containers while dotnet services get rebuilt/restarted as needed. Source from `github.com/saltworks/saltminer` is cloned to VM and mounted into containers for symbol resolution.

---

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Ubuntu 24 VM (Remote)                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Docker Compose (debug mode)                            │ │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────────┐  │ │
│  │  │ api     │ │ ui-api  │ │ services │ │ jobmanager  │  │ │
│  │  │ :4024   │ │ :4025   │ │ :4026    │ │ :4027       │  │ │
│  │  │ (vsdbg) │ │ (vsdbg) │ │ (vsdbg)  │ │ (vsdbg)     │  │ │
│  │  └────┬────┘ └────┬────┘ └────┬─────┘ └──────┬──────┘  │ │
│  │       └───────────┴───────────┴──────────────┘         │ │
│  │                    │                                   │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────┐  │ │
│  │  │ nginx   │ │ es01    │ │ kibana  │ │ dev-control  │  │ │
│  │  │ :443    │ │ :9200   │ │ :5601   │ │ :8080 (API)  │  │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └──────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
│  /home/dev/saltminer (source code)                          │
│  /home/dev/saltminer-setup (configs)                        │
└─────────────────────────────────────────────────────────────┘
         │                          │
    SSH (22)                   Debug Ports (4024-4028)
         │                          │
┌────────┴──────────────────────────┴─────────────────────────┐
│  Developer Workstation                                      │
│  ┌────────────┐  ┌───────────────────────────────────────┐  │
│  │ VS Code    │  │ Visual Studio 2022                    │  │
│  │ +Remote-SSH│  │ +Linux Remote Debugging               │  │
│  │ +Docker ext│  │ (optional)                            │  │
│  │ +Copilot   │  │                                       │  │
│  └────────────┘  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

### Steps

**Phase 1: VM & Base Infrastructure**

1. **Provision Ubuntu 24 VM** with Docker Engine and Docker Compose v2, SSH enabled, ports open: 22 (SSH), 443 (nginx), 9200 (ES), 4024-4028 (debug), 8080 (dev-control API)

2. **Clone repositories** to VM:
   - `git clone github.com/saltworks/saltminer ~/saltminer` (source)
   - `git clone [setup-repo] ~/saltminer-setup` (configs)

3. **Create Docker network and volumes** for debug environment (matching production topology)

**Phase 2: Debug-Enabled Container Images**

4. **Create Dockerfile.debug** for each .NET app (extend base images):
   - Install `vsdbg` debugger: `curl -sSL https://aka.ms/getvsdbgsh | bash /dev/stdin -v latest -l /vsdbg`
   - Set `ASPNETCORE_ENVIRONMENT=Development`
   - Keep debug symbols (PDBs) in image OR mount from source

5. **Build debug images** via Makefile or build script:
   - `saltminer-api:debug`, `saltminer-ui-api:debug`, etc.
   - Include build-time flags: `dotnet publish -c Debug`

**Phase 3: Debug Compose File**

6. **Create `docker-compose.debug.yml`** in saltminer-setup with:
   - Debug image tags for all .NET services
   - Exposed debug ports per service (4024-4028)
   - Source code bind mounts: `~/saltminer/src:/app/src:ro`
   - Console logging enabled in addition to file logging
   - `stdin_open: true` and `tty: true` for interactive debugging
   - Entrypoint modified to wait for debugger attach OR start normally

7. **Configure services not to auto-restart** during debug (`restart: "no"`)

**Phase 4: Dev-Control Orchestration API**

8. **Build small FastAPI/Flask service** (`dev-control`) that exposes:
   - `POST /services/{name}/restart` - restart single service
   - `POST /services/{name}/rebuild` - rebuild and restart
   - `POST /services/restart-all` - restart all dotnet services
   - `GET /services/{name}/logs?tail=100` - fetch recent logs
   - `GET /services/{name}/status` - health/debug status
   - `POST /debug/{name}/attach-ready` - signal waiting for debugger
   - `WebSocket /logs/{name}` - live log streaming

9. **Add dev-control to compose** with access to Docker socket

**Phase 5: VS Code Configuration**

10. **Create `.vscode/launch.json`** in saltminer repo with debug configurations:
    - "Attach to API (Remote Docker)"
    - "Attach to UI-API (Remote Docker)"
    - "Attach to ServiceManager (Remote Docker)"
    - "Attach to JobManager (Remote Docker)"
    - Compound launch config for multi-service debugging

11. **Create `.vscode/tasks.json`** with:
    - "Restart API" - calls dev-control API
    - "Rebuild All Services"
    - "Tail API Logs"

12. **Document Remote-SSH setup** for connecting to Ubuntu VM

**Phase 6: Visual Studio Support (Optional Enhancement)**

13. **Configure Visual Studio remote debugging**:
    - SSH connection to VM
    - Attach to running process via vsdbg
    - Map source paths to local Windows paths
    - Create `.suo` settings for team sharing

**Phase 7: Logging & AI Visibility**

14. **Configure Serilog** in `appsettings.Development.json`:
    - Console sink (for `docker compose logs -f`)
    - File sink to mounted volume (for persistence)
    - Debug level minimum
    - Include source context and exception details

15. **Create log aggregation approach**:
    - Option A: Copilot reads logs via VS Code terminal (docker compose logs -f)
    - Option B: dev-control API exposes logs endpoint for AI tools
    - Option C: MCP server wrapping dev-control for direct Claude integration

**Phase 8: Quick Iteration Workflow**

16. **Create helper scripts** in saltminer repo:
    - `scripts/debug-start.sh` - bring up full debug environment
    - `scripts/debug-restart.sh <service>` - hot-restart single service
    - `scripts/debug-rebuild.sh <service>` - rebuild container from source
    - `scripts/debug-logs.sh <service>` - tail logs

17. **Document the debug workflow**:
    ```
    1. VS Code: Remote-SSH to VM
    2. Open ~/saltminer folder
    3. Terminal: ./scripts/debug-start.sh (first time)
    4. Make code changes
    5. F5 or Ctrl+Shift+P → "Restart API"
    6. Set breakpoints, attach debugger
    7. Copilot can read logs in terminal panel
    ```

---

### Verification

- **Connectivity test**: SSH to VM, verify Docker running, ports accessible
- **Debug attach test**: Start API in debug mode, attach VS Code debugger, hit breakpoint
- **Multi-debug test**: Attach to both API and UI-API simultaneously, step through cross-service call
- **Hot-restart test**: Change code → run restart task → verify change reflected in <30 seconds
- **AI visibility test**: Copilot can answer questions about recent log output
- **Visual Studio test** (if implemented): Attach from Windows VS to Linux container

---

### Decisions to Finalize

| Decision | Options | Impact |
|----------|---------|--------|
| **Debug port allocation** | Static (4024-4028) vs dynamic | Static is simpler for launch.json |
| **Source mounting** | Full repo mount vs build artifacts only | Full mount enables hot-reload for some scenarios |
| **Dev-control API** | Python (FastAPI) vs Go vs Node | FastAPI recommended for quick dev, good AI tooling |
| **AI log access** | Terminal tailing vs API endpoint vs MCP | Terminal simplest, MCP most powerful |

---

### Open Questions

1. Does the saltminer repo have a solution file structure I should review for accurate debug configs?
2. Any existing CI/CD pipeline for building images that debug builds should integrate with?
3. Preferred IDE extensions beyond standard Docker/Remote-SSH for VS Code?

---

**Ready for your feedback.** I can refine any section, explore alternatives (like running dotnet directly on VM without containers), or dive deeper into a specific component.
