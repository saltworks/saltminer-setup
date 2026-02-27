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

### 5. Install venv for python

```bash
sudo apt install -y python3.12-venv
```

### 6. Validate vsdbg-over-SSH (IMPORTANT — do this before containers)

Before wiring up containers, confirm the core debugging pipeline works. This uses a standalone test .NET app to validate that VS Code can attach vsdbg through an SSH connection.

**See [PROTOTYPE-TEST.md](PROTOTYPE-TEST.md) for detailed, step-by-step instructions.**

Quick summary:

1. **On the VM**, create a simple test app:
   ```bash
   mkdir -p ~/vsdbg-prototype && cd ~/vsdbg-prototype
   dotnet new console -n PrototypeTest && cd PrototypeTest
   # Replace Program.cs with a loop (see PROTOTYPE-TEST.md)
   dotnet build -c Debug
   dotnet run -c Debug &  # Leave running
   ```

2. **On your workstation**, create a local workspace:
   ```powershell
   mkdir -p ~\vsdbg-prototype-test\prototype-test
   code ~\vsdbg-prototype-test
   # Copy launch.json.prototype-test to .vscode/launch.json and edit hostname
   ```

3. **Test debugging:** Press F5 → VS Code automatically initiates SSH connection → debugger should attach

**Success criteria:** Breakpoint hits, variables are inspectable, step-over/into work correctly.

If this test passes, the `pipeTransport` mechanism is validated and ready for production containers. If it fails, troubleshoot SSH connectivity and vsdbg installation using the detailed guide before proceeding.

### 6. Configure .csproj paths in Dockerfiles

The Dockerfiles are located in **this repo** (saltminer-setup) at `/opt/saltminer-dev/saltminer-setup/devops/dev-containers/.dockerfiles/`. They contain `# TODO: Verify .csproj path` comments. Open each Dockerfile and verify the paths are correct.

**Example:** If `Saltworks.SaltMiner.DataApi.csproj` is at `/opt/saltminer-dev/saltminer/Saltworks.SaltMiner.DataApi/Saltworks.SaltMiner.DataApi/Saltworks.SaltMiner.DataApi.csproj`, verify the `RUN dotnet publish` line in `Dockerfile.debug.api` to use `Saltworks.SaltMiner.DataApi/Saltworks.SaltMiner.DataApi/Saltworks.SaltMiner.DataApi.csproj` (path relative to the saltminer repo root, since that's the Docker build context).

### 7. Deploy Flask orchestration API

```bash
# Create the dedicated service account used by saltminer-dev-api.service
sudo useradd -r -s /bin/false -d /opt/saltminer-dev/control-api saltminer
# Add saltminer to the docker group so it can run docker commands
sudo usermod -aG docker saltminer

cp -r /opt/saltminer-dev/saltminer-setup/devops/dev-containers/orchestration-api /opt/saltminer-dev/control-api
sudo chown -R saltminer:saltminer /opt/saltminer-dev/control-api
cd /opt/saltminer-dev/control-api
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt

# Create .env from example
mv .env.example .env
# Edit .env: set a strong API_KEY and set SM_SERVICES_IMAGE_VERSION to match saltminer-setup/.env
nano .env

# Install and start systemd service
sudo cp saltminer-dev-api.service /etc/systemd/system/
sudo chmod 755 run-api.sh
sudo systemctl daemon-reload
sudo systemctl enable --now saltminer-dev-api

# Verify it started
sudo systemctl status saltminer-dev-api
curl http://localhost:8080/api/status
```

### 8. Start stable infrastructure (Elasticsearch + Kibana)

ELK runs from its own compose file (`devops/dev-containers/docker-compose-elk.yml`) so versions can be updated independently from the application services.

Before starting ELK components, edit file (`devops/dev-containers/.env`) and set the KIBANA_URL variable to the public kibana URL needed for the stack.

```bash
cd /opt/saltminer-dev/saltminer-setup
docker compose \
  --env-file devops/dev-containers/.env \
  -f devops/dev-containers/docker-compose-elk.yml \
  up setup es01 kibana nginx -d
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

### Access SaltMiner UI and APIs via nginx

Nginx is included in the ELK stack (`docker-compose-elk.yml`) and reverse-proxies all services on port 80:

| Path | Target |
|------|--------|
| `http://localhost/` | Kibana |
| `http://localhost/smapi/` | DataApi |
| `http://localhost/smuiapi/` | UiApi |
| `http://localhost/smpgui/` | Vite dev server (with HMR) |

This is the entry point for Manager and SyncAgent testing — configure those tools to point at `http://localhost/smapi/` and `http://localhost/smuiapi/`.

### Debug Vue.js frontend

1. Ensure `smpgui` (Vite) is running — navigate to `http://localhost/smpgui/` (via nginx) or `http://localhost:5173` (direct)
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
# Branch name goes in the URL path. After checkout, rebuild affected services.
curl -X POST -H "X-API-Key: <key>" \
  http://localhost:8080/api/repo/checkout/feature/my-branch

# Then rebuild:
curl -X POST -H "X-API-Key: <key>" http://localhost:8080/api/services/rebuild-all
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
