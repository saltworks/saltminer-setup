# Design: Remote Ubuntu 24 Dev Environment with Debug Docker Containers

## Original Prompt (Claude)
/superpowers:brainstorm Create a remote Ubuntu 24 dev environment with debug-enabled Docker containers. VS Code connects via Remote-SSH, attaches debuggers to .NET apps via vsdbg. A small orchestration API enables quick start/stop/rebuild cycles controllable by both humans and AI. Elasticsearch/Kibana remain stable containers while dotnet services get rebuilt/restarted as needed. Source from `github.com/saltworks/saltminer` is cloned to VM and mounted into containers for symbol resolution.

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  DEV WORKSTATION                                                              │
│                                                                               │
│  ┌──────────────────────────────┐   ┌──────────────────────────────────────┐  │
│  │  VS Code                     │   │  Browser                             │  │
│  │  ├── Remote-SSH extension    │   │  ├── http://localhost:5173  (Vite UI)│  │
│  │  ├── C# / OmniSharp          │   │  └── http://localhost:8080  (Flask   │  │
│  │  ├── Vue / TypeScript        │   │       dashboard)                     │  │
│  │  └── launch.json             │   └──────────────┬───────────────────────┘  │
│  │       ├── Attach: api        │                  │ port-forwarded via SSH   │
│  │       ├── Attach: ui-api     │                  │                          │
│  │       ├── Attach: sm-services│                  │                          │
│  │       ├── Attach: jobmanager │                  │                          │
│  │       └── Debug: UI (Chrome) │                  │                          │
│  └──────────┬───────────────────┘                  │                          │
│             │ SSH (Remote-SSH)                     │                          │
└─────────────┼──────────────────────────────────────┼──────────────────────────┘
              │                                      │
              ▼ SSH tunnel / port-forwarding         │
┌───────────────────────────────────────────────────────────────────────────────┐
│  UBUNTU 24 VM                                                                 │
│                                                                               │
│  /opt/saltminer-dev/                                                          │
│  ├── saltminer-setup/      (this repo — config, compose, Dockerfiles)         │
│  └── saltminer/            (saltworks/saltminer source — .cs, .vue files)     │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐   │
│  │  Flask Orchestration API  (systemd: saltminer-dev-api, :8080)          │   │
│  │  GET  /                      → HTML dashboard                          │   │
│  │  GET  /api/services          → service status                          │   │
│  │  POST /api/services/{n}/rebuild                                        │   │
│  │  POST /api/services/{n}/start|stop                                     │   │
│  │  POST /api/services/rebuild-all                                        │   │
│  │  POST /api/ui/restart                                                  │   │
│  │  POST /api/repo/checkout     → git checkout on saltminer source        │   │
│  └────────────────────────────────┬───────────────────────────────────────┘   │
│                                   │ docker compose + subprocess               │
│  ┌────────────────────────────────▼───────────────────────────────────────┐   │
│  │  DOCKER  (network: saltminer)                                          │   │
│  │                                                                        │   │
│  │  ┌──── STABLE (always on) ─────────────────────────────────────────┐   │   │
│  │  │  sm-es01     Elasticsearch   :9200                              │   │   │
│  │  │  sm-kibana   Kibana          :5601                              │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                        │   │
│  │  ┌──── DEBUG (managed by Flask API) ───────────────────────────────┐   │   │
│  │  │  sm-api          DataApi        :5000  ← vsdbg                  │   │   │
│  │  │  sm-ui-api       UiApi          :5001  ← vsdbg                  │   │   │
│  │  │  sm-sm-services  ServiceManager         ← vsdbg                 │   │   │
│  │  │  sm-jobmanager   JobManager             ← vsdbg                 │   │   │
│  │  │  sm-ui           Vite dev server :5173  ← CDP  :9229            │   │   │
│  │  │                                                                 │   │   │
│  │  │  All debug containers mount:                                    │   │   │
│  │  │    /opt/saltminer-dev/saltminer → /src  (symbols + source)      │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Key flows:**
- `.NET debug` → VS Code pipeTransport → SSH → `docker exec sm-api` → vsdbg → attach to `dotnet`
- `Vue debug` → VS Code Chrome debugger → port-forward :5173 → Vite → CDP → source maps
- `AI/human control` → HTTP POST → Flask API (:8080) → `docker compose` subprocess
- `Source code` bind-mounted into all containers at `/src` for live symbol resolution

> **Note:** This design uses **pipe transport** (stdin/stdout), so vsdbg does not listen on any TCP ports. See the [vsdbg Setup and Communication](#vsdbg-setup-and-communication) section for details.

---

## Context

SaltMiner is currently deployed as pre-built production Docker images pulled from Docker Hub. There is no development workflow for attaching debuggers, iterating on code, or running the Vue.js frontend from source. This design creates a self-contained development environment on a remote Ubuntu 24 VM where:

- VS Code connects via Remote-SSH and attaches .NET debuggers (vsdbg) to all four .NET services
- The Vue.js frontend runs from source via Vite dev server with TypeScript debugging support
- Elasticsearch and Kibana remain as stable always-on containers
- A Flask orchestration API provides start/stop/rebuild control for both humans and AI (Claude Code)
- All new infrastructure lives in `devops/dev-containers/` in the `saltminer-setup` repo

---

## File Layout

```
devops/ai-plans/
└── remote-debug-env.md                    ← this design doc

devops/dev-containers/
├── README.md                              ← VM setup instructions + usage guide
├── docker-compose-debug.yml               ← compose override for debug services
├── .dockerfiles/
│   ├── Dockerfile.debug.api               ← DataApi hybrid debug image
│   ├── Dockerfile.debug.ui-api            ← UiApi hybrid debug image
│   ├── Dockerfile.debug.sm-services       ← ServiceManager hybrid debug image
│   ├── Dockerfile.debug.jobmanager        ← JobManager hybrid debug image
│   └── Dockerfile.debug.ui               ← Node.js + Vite dev server
├── orchestration-api/
│   ├── app.py                             ← Flask REST API + web UI
│   ├── templates/
│   │   └── index.html                     ← HTML dashboard (buttons per service)
│   ├── config.py                          ← Service definitions, paths
│   ├── requirements.txt                   ← flask, python-dotenv
│   ├── saltminer.http                     ← VS Code / httpyac request file
│   └── saltminer-dev-api.service         ← systemd unit (port 8080)
└── vscode-templates/
    ├── launch.json.template               ← 4 .NET attach + 1 Chrome debug config
    ├── tasks.json.template                ← rebuild/restart tasks via curl
    └── settings.json.template            ← remote host settings
```

`.vscode/` files are `.gitignored` in the saltminer repo. Developers copy from templates and customize locally.

---

## Debug Dockerfiles (Hybrid Pattern)

Each .NET service uses a two-stage build. Stage 1 compiles from source in Debug mode; Stage 2 layers the Debug artifacts onto the production base image and installs vsdbg.

```dockerfile
# Stage 1: Debug build from source
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish src/SaltMiner.<Service>/<Service>.csproj \
    -c Debug -o /app/debug

# Stage 2: Prod image base + debug layer
FROM docker.io/saltworks/saltminer:${SM_<SERVICE>_IMAGE_VERSION} AS final
WORKDIR /app
COPY --from=build /app/debug ./
RUN apt-get update && apt-get install -y curl unzip \
 && curl -sSL https://aka.ms/getvsdbgsh | bash /dev/stdin -v latest -l /vsdbg \
 && rm -rf /var/lib/apt/lists/*
ENV ASPNETCORE_ENVIRONMENT=Development
ENV DOTNET_ENABLE_DIAGNOSTICS=1
```

Source tree bind-mounted into each container for symbol resolution:
```yaml
volumes:
  - /opt/saltminer-dev/saltminer:/src:ro
```

The Vue.js dev container runs the Vite dev server with HMR:
```dockerfile
FROM node:20-alpine
WORKDIR /app
# Source is bind-mounted at runtime so edits on VM are live
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

## vsdbg Setup and Communication

### Pipe Transport vs. Server Mode

This design uses **pipe transport** for vsdbg, not server mode. Here's how it works:

#### Pipe Transport Method (Used in This Design)

**How it works:**
1. VS Code uses `pipeTransport` in `launch.json` to invoke vsdbg remotely via SSH or `docker exec`
2. vsdbg communicates through **stdin/stdout** over the pipe, not via TCP sockets
3. No network ports are opened or listened on by vsdbg
4. The debugging protocol flows through the SSH connection or Docker exec pipe

**Example flow:**
```
VS Code → SSH → docker exec -i sm-api /vsdbg/vsdbg --interpreter=vscode
                  ↑                            ↓
                  stdin/stdout pipe for debug protocol
```

**Container configuration (no ports needed):**
```dockerfile
# Install vsdbg to /vsdbg/ directory
RUN curl -sSL https://aka.ms/getvsdbgsh | bash /dev/stdin -v latest -l /vsdbg

# No EXPOSE directive needed for vsdbg
# No CMD to start vsdbg as a daemon
# vsdbg is invoked on-demand by the debugger
```

**launch.json configuration:**
```json
{
  "type": "coreclr",
  "request": "attach",
  "pipeTransport": {
    "pipeProgram": "docker",
    "pipeArgs": ["exec", "-i", "sm-api"],
    "debuggerPath": "/vsdbg/vsdbg"
  }
}
```

**Advantages:**
- No port management or firewall rules needed
- Works seamlessly with Docker and SSH without additional networking setup
- More secure (no exposed debug ports)
- Simpler configuration

#### Server Mode (Alternative, Not Used Here)

In server mode, vsdbg runs as a daemon and listens on a TCP port. This requires:
- Container exposes port (e.g., `EXPOSE 4024`)
- docker-compose maps port: `ports: ["4024:4024"]`
- vsdbg started with `--server-port`: `vsdbg --server-port=4024`
- launch.json uses `"debugServer": 4024` instead of `pipeTransport`

**We are NOT using server mode** in this design because pipe transport is simpler and doesn't require port management.

### SSH Authentication Options

VS Code's `pipeTransport` supports both key-based and password authentication:

#### SSH Key-Based Authentication (Recommended)

**Setup:**
1. **Generate SSH key on workstation** (if not exists):
   ```powershell
   ssh-keygen -t ed25519 -C "your-email@example.com"
   ```

2. **Copy public key to VM:**
   ```powershell
   ssh-copy-id user@vm-hostname
   # Or manually: Get-Content ~\.ssh\id_ed25519.pub | ssh user@vm-hostname "cat >> ~/.ssh/authorized_keys"
   ```

3. **Test passwordless login:**
   ```powershell
   ssh user@vm-hostname "echo Connected successfully"
   ```

4. **VS Code SSH config** (`~/.ssh/config` or `C:\Users\YourName\.ssh\config`):
   ```
   Host saltminer-dev
       HostName 192.168.1.100
       User developer
       IdentityFile ~/.ssh/id_ed25519
       ForwardAgent yes
   ```

**Advantages:**
- No password prompts during debugging sessions
- Secure and faster
- Required for automated/AI-driven workflows via the orchestration API
- Standard best practice

#### Username/Password Authentication (Possible but Not Recommended)

VS Code can use password authentication but requires additional configuration:

**Option A: SSH Agent with password caching**
```bash
# Start ssh-agent and add key (prompts for password once per session)
eval $(ssh-agent)
ssh-add ~/.ssh/id_ed25519
```

**Option B: VS Code extension settings**
In VS Code settings.json:
```json
{
  "remote.SSH.showLoginTerminal": true,
  "remote.SSH.useLocalServer": false
}
```

This causes VS Code to show a terminal for manual password entry.

**Disadvantages:**
- Frequent password prompts interrupt debugging workflow
- Not suitable for AI agent automation
- Less secure (passwords in transit, even over SSH)
- More complex setup

### Docker Exec Pipe Transport

Once connected to the VM via Remote-SSH, the debugger uses Docker's stdin/stdout to communicate with vsdbg inside containers:

```json
"pipeTransport": {
  "pipeProgram": "docker",           // ← Runs on the VM (not your workstation)
  "pipeArgs": ["exec", "-i", "sm-api"],  // ← -i keeps stdin open
  "debuggerPath": "/vsdbg/vsdbg",    // ← Path inside container
  "pipeCwd": "${workspaceRoot}"
}
```

**No SSH configuration needed here** because VS Code is already connected to the VM via Remote-SSH extension. The `docker` command runs locally on the VM.

### Environment Variables for Debug

The Dockerfiles set these environment variables to enable debugger compatibility:

```dockerfile
ENV ASPNETCORE_ENVIRONMENT=Development
ENV DOTNET_ENABLE_DIAGNOSTICS=1
```

These ensure:
- ASP.NET Core runs in Development mode (more verbose logging, dev exception pages)
- .NET diagnostics ports are available for vsdbg to attach
- No additional configuration needed in `appsettings.json`

### Port Summary

**Ports that ARE used:**
- `5000-5001` — ASP.NET Core apps (HTTP APIs)
- `5173` — Vite dev server (Vue.js UI)
- `8080` — Flask orchestration API
- `9200` — Elasticsearch
- `5601` — Kibana

**Ports that are NOT used:**
- `4024-4027` — vsdbg (shown in architecture diagram for documentation only)
- `9229` — Chrome DevTools Protocol (used internally by Vite, not exposed)

---

## docker-compose-debug.yml

Override file extending `docker-compose-local.yml`. Replaces the four .NET service image definitions with locally-built debug images and adds the Vue.js UI dev container.

Run command (handled internally by Flask API):
```bash
docker compose \
  -f /opt/saltminer-dev/saltminer-setup/docker-compose-local.yml \
  -f /opt/saltminer-dev/saltminer-setup/devops/dev-containers/docker-compose-debug.yml \
  up -d [service_name]
```

---

## Flask Orchestration API

**Runtime:** Python 3 + Flask, runs as `saltminer-dev-api.service` on port `8080`. Deployed to `/opt/saltminer-dev-api/` on the VM.

**Auth:** Static `X-API-Key` header required for all write (POST) operations. GET endpoints are unrestricted. API key configured in `.env`.

### Endpoints

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/` | HTML dashboard (web UI) |
| `GET` | `/api/status` | Overall stack health |
| `GET` | `/api/services` | List all services with status |
| `POST` | `/api/services/{name}/start` | Start one service |
| `POST` | `/api/services/{name}/stop` | Stop one service |
| `POST` | `/api/services/{name}/rebuild` | `docker build` → stop → start |
| `POST` | `/api/services/rebuild-all` | Rebuild all 5 debug services |
| `GET` | `/api/services/{name}/logs` | Tail logs (`?lines=100`) |
| `POST` | `/api/ui/restart` | Restart ui container (on startup, `npm install`, `npm run dev`) |
| `POST` | `/api/repo/checkout/{branch}` | `git checkout {branch}` on saltminer source |

Valid service names: `api`, `ui-api`, `sm-services`, `jobmanager`, `ui`

### Web UI (`GET /`)

Single-page HTML dashboard served by Flask (no JS framework). Shows a status table of all services with Start / Stop / Rebuild buttons per row, plus global Rebuild All and Restart UI buttons. Branch checkout form at the bottom. Buttons call REST endpoints via `fetch()`. The API key is stored as a pre-filled input on the page.

### `.http` File

`saltminer.http` covers all endpoints with `{{baseUrl}}` and `{{apiKey}}` variable substitution, compatible with VS Code REST Client and httpyac:

```http
@baseUrl = http://remote-server:8080
@apiKey = changeme

### Status
GET {{baseUrl}}/api/status

### List services
GET {{baseUrl}}/api/services

### Start api
POST {{baseUrl}}/api/services/api/start
X-API-Key: {{apiKey}}

### Stop api
POST {{baseUrl}}/api/services/api/stop
X-API-Key: {{apiKey}}

### Rebuild api
POST {{baseUrl}}/api/services/api/rebuild
X-API-Key: {{apiKey}}

### Rebuild all
POST {{baseUrl}}/api/services/rebuild-all
X-API-Key: {{apiKey}}

### Get api logs
GET {{baseUrl}}/api/services/api/logs?lines=100

### Restart UI
POST {{baseUrl}}/api/ui/restart
X-API-Key: {{apiKey}}

### Checkout branch
POST {{baseUrl}}/api/repo/checkout/main
X-API-Key: {{apiKey}}
```

---

## VS Code Integration

Templates in `devops/dev-containers/vscode-templates/`. Developers copy to `saltminer/.vscode/` and customize (`.vscode/` is `.gitignored` in saltminer).

### launch.json.template — 5 configurations

**.NET attach (×4):** `coreclr` type, `pipeTransport` via `docker exec <container>`, vsdbg at `/vsdbg/vsdbg`, `sourceFileMap: { "/src": "${workspaceRoot}" }`.

```json
{
  "name": "Attach: api",
  "type": "coreclr",
  "request": "attach",
  "processName": "dotnet",
  "pipeTransport": {
    "pipeProgram": "docker",
    "pipeArgs": ["exec", "-i", "sm-api"],
    "debuggerPath": "/vsdbg/vsdbg",
    "pipeCwd": "${workspaceRoot}"
  },
  "sourceFileMap": { "/src": "${workspaceRoot}" }
}
```

**Vue/TypeScript (Chrome CDP):**
```json
{
  "name": "Debug: UI (Chrome)",
  "type": "chrome",
  "request": "launch",
  "url": "http://localhost:5173",
  "sourceMapPathOverrides": {
    "/app/*": "${workspaceRoot}/src/SaltMiner.Ui/*"
  }
}
```

### tasks.json.template

Tasks calling `curl -H "X-API-Key: ..." http://localhost:8080/api/...` for rebuild, restart, and log tailing. Allows one-click operations from VS Code's command palette.

### settings.json.template

```json
{
  "remote.SSH.defaultForwardedPorts": [
    { "localPort": 8080, "remotePort": 8080, "name": "Flask API" },
    { "localPort": 5173, "remotePort": 5173, "name": "Vite Dev Server" }
  ]
}
```

---

## VM Setup Steps

### Prerequisites (one-time)

1. Install Docker + docker-compose-plugin
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   ```

2. Install .NET SDK 8.0
   ```bash
   wget https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb
   sudo dpkg -i packages-microsoft-prod.deb
   sudo apt-get install -y dotnet-sdk-8.0
   ```

3. Install Python 3 + pip, git (usually pre-installed on Ubuntu 24)

4. Clone repos
   ```bash
   sudo mkdir -p /opt/saltminer-dev
   sudo chown $USER /opt/saltminer-dev
   git clone <saltminer-setup-repo> /opt/saltminer-dev/saltminer-setup
   git clone https://github.com/saltworks/saltminer /opt/saltminer-dev/saltminer
   ```

5. Install vsdbg on VM host (for prototype validation step below)
   ```bash
   curl -sSL https://aka.ms/getvsdbgsh | sudo bash /dev/stdin -v latest -l /vsdbg
   ```

### Prototype Step — Validate vsdbg-over-SSH Before Docker

Before wiring up containers, confirm the VS Code → SSH → vsdbg pipeline works. This validates the core debugging mechanism without Docker complexity.

#### On the VM

1. **Create a test .NET console app:**
   ```bash
   mkdir -p /tmp/vsdbg-test && cd /tmp/vsdbg-test
   dotnet new console -n PrototypeTest
   cd PrototypeTest
   ```

2. **Replace `Program.cs` with breakpoint-friendly code:**
   ```bash
   cat > Program.cs << 'EOF'
   namespace PrototypeTest;
   
   class Program
   {
       static void Main(string[] args)
       {
           Console.WriteLine("Starting vsdbg prototype test...");
           
           for (int i = 0; i < 100; i++)
           {
               DoWork(i);  // ← Set breakpoint here or in DoWork()
               Thread.Sleep(2000);
           }
       }
       
       static void DoWork(int iteration)
       {
           var message = $"Iteration {iteration} at {DateTime.Now:HH:mm:ss}";
           Console.WriteLine(message);  // ← Or set breakpoint here
       }
   }
   EOF
   ```

3. **Build in Debug mode and run with an identifiable process name:**
   ```bash
   dotnet build -c Debug
   dotnet run -c Debug --no-build --project PrototypeTest.csproj &
   ```
   
   The process will be named `PrototypeTest` (matching the project name) which makes it easier for vsdbg to attach.

4. **Verify the process is running:**  Make sure you see "Iteration X at hh:mm:ss" statements.
   
#### On the Workstation

1. **Create a local workspace folder to mirror the VM structure:**
   ```powershell
   mkdir -p ~\vsdbg-prototype-test\prototype-test
   ```

2. **Copy the source file locally** (needed for symbol resolution):
   ```powershell
   # Use scp or manually copy the Program.cs from the VM
   scp your-vm-hostname:/tmp/vsdbg-test/PrototypeTest/Program.cs ~\vsdbg-prototype-test\prototype-test\
   ```

3. **Open the prototype workspace in VS Code:**
   ```powershell
   code ~\vsdbg-prototype-test
   ```

4. **Copy the prototype launch.json:**
   Copy `devops/dev-containers/vscode-templates/launch.json.prototype-test` to `.vscode/launch.json` in your prototype workspace, then edit:
   
   ```json
   {
     "pipeArgs": [
       "your-actual-vm-hostname-or-ip",  // ← Change this
       "-T"
     ],
   }
   ```

5. **SSH Connection Behavior:**

   When you press `F5` to start debugging:
   - VS Code **automatically initiates an SSH connection** using `ssh your-vm-hostname -T`
   - The SSH connection opens a pipe for communication with vsdbg
   - **You do NOT need to manually connect to the VM first**
   - SSH keys must be set up for passwordless auth (see [SSH-SETUP.md](SSH-SETUP.md))
   - The SSH connection remains open for the duration of the debug session
   - When you stop debugging, the SSH connection closes

   **In other words:** Just press F5, and the launch.json will handle the SSH connection for you.

6. **Test the connection:**
   - Set a breakpoint in `Program.cs` on line 9 (`DoWork(i);`) or line 16 (`Console.WriteLine(message);`)
   - Press `F5` or select **Run → Start Debugging**
   - Select "Prototype: Attach vsdbg over SSH"
   - VS Code will prompt for SSH host confirmation on first connection (accept by typing `yes`)
   - Should attach vsdbg and hit your breakpoint
   - Verify the call stack, variables window, and step-through all work

7. **Troubleshooting:**
   - If connection fails with "Unable to attach", verify SSH keys are set up (passwordless auth required)
   - If connection fails with "Could not establish connection", check hostname is correct: `ping your-vm-hostname`
   - If process not found, check `processName` matches: run `ssh vm-hostname "ps aux | grep PrototypeTest"` from workstation
   - If source not mapped, verify `sourceFileMap` matches your local folder structure
   - Add `"logging": { "engineLogging": true }` to the launch config to see vsdbg diagnostics

8. **Clean up when done:**
   ```bash
   # On VM
   pkill -f PrototypeTest
   rm -rf /tmp/vsdbg-test
   ```

**Success criteria:** Breakpoint hits, variables are inspectable, step-over/into work correctly. Once validated, the same `pipeTransport` pattern will be used in `launch.json.template` with `docker exec` instead of direct SSH.

### Remote Development Workflow

For the actual containerized development environment:

1. **First-time setup:** Use VS Code Remote-SSH to connect to the VM
   - `F1` → "Remote-SSH: Connect to Host" → select `saltminer-dev`
   - This opens a VS Code window running on the remote VM

2. **Once connected via Remote-SSH:**
   - Open `/opt/saltminer-dev/saltminer` as workspace
   - Copy `launch.json.template` → `saltminer/.vscode/launch.json`
   - Edit to use `docker exec` (instead of direct SSH)
   - `docker` command now runs on the VM via the established Remote-SSH connection
   - **No additional SSH connections needed** — all `docker exec` commands use the current Remote-SSH session

3. **Why this is different from prototype:**
   - **Prototype:** Each F5 press creates a temporary SSH connection
   - **Production:** You stay connected to the VM via Remote-SSH; `docker exec` uses that connection
   - **Result:** Same pipe transport mechanism, but leveraging Remote-SSH's persistent connection

### Flask API Setup

```bash
cp -r /opt/saltminer-dev/saltminer-setup/devops/dev-containers/orchestration-api /opt/saltminer-dev-api
cd /opt/saltminer-dev-api
pip3 install -r requirements.txt
cp .env.example .env        # set API_KEY
sudo cp saltminer-dev-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saltminer-dev-api
```

### Start Stable Infrastructure

```bash
cd /opt/saltminer-dev/saltminer-setup
docker compose -f docker-compose-local.yml up es01 kibana -d
```

### Build and Start Debug Services

```bash
curl -X POST -H "X-API-Key: <key>" http://localhost:8080/api/services/rebuild-all
```

### VS Code Workspace

1. Add SSH host to `~/.ssh/config` on workstation
2. VS Code: Connect to Host → open `/opt/saltminer-dev/saltminer`
3. Copy `devops/dev-containers/vscode-templates/*.template` → `saltminer/.vscode/` (remove `.template` suffix), customize VM hostname

---

## Verification

1. `GET http://localhost:8080/api/status` — all 7 services show healthy
2. `GET http://localhost:8080/` — dashboard loads, service statuses shown
3. VS Code Remote-SSH opens `saltminer/` workspace without error
4. Set breakpoint in `DataApi`, run "Attach: api" → breakpoint hits on a request
5. Navigate to `http://localhost:5173` → Vue.js UI loads, connects to ui-api
6. Set breakpoint in a `.vue` component, run "Debug: UI (Chrome)" → breakpoint hits
7. `POST /api/repo/checkout {"branch": "feature/x"}` → source updates → `rebuild-all` → new code running
8. `POST /api/ui/restart` → UI container restarts, HMR resumes
