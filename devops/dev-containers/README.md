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
