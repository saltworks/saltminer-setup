# Prototype: Validate vsdbg over SSH

Before wiring up containers, confirm the core debugging pipeline works. This validates that VS Code can attach vsdbg through an SSH connection by using a simple standalone .NET console application.

## Why This Step?

- Isolates the "SSH + vsdbg" mechanism from Docker complexity
- Catches SSH key/authentication issues early
- Proves that the `pipeTransport` debugging model works
- Quick feedback loop (no container builds)

## On the VM

### 1. Create a test .NET console app

```bash
mkdir -p ~/vsdbg-prototype && cd ~/vsdbg-prototype
dotnet new console -n PrototypeTest
cd PrototypeTest
```

### 2. Replace Program.cs with breakpoint-friendly code

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

The loop keeps the process alive for 200 seconds, giving you time to attach the debugger.

### 3. Build in Debug mode and run

```bash
dotnet build -c Debug
dotnet run -c Debug --no-build --project PrototypeTest.csproj &
```

You should see output like:
```
Starting vsdbg prototype test...
Iteration 0 at 14:23:45
Iteration 1 at 14:23:47
Iteration 2 at 14:23:49
...
```

The process name is `PrototypeTest` (matching the project name), which makes it easier for vsdbg to identify it.

### 4. Verify the process is running

Press enter and then enter the command - output from the program will continue to print to the console during this step.

```bash
ps aux | grep PrototypeTest
```

You should see the dotnet process running.

## On the Workstation

### 1. Create a local workspace folder

```powershell
mkdir -p ~\vsdbg-prototype-test\prototype-test
cd ~\vsdbg-prototype-test
```

### 2. Copy the source file from the VM

Copy `Program.cs` from the VM to your local workspace. You can do this with `scp` or manually:

```powershell
# Using scp (if available on Windows)
scp your-vm-hostname:~/vsdbg-prototype/PrototypeTest/Program.cs ~\vsdbg-prototype-test\prototype-test\

# Or use WSL / Git Bash equivalent
```

You need the source file locally so VS Code can match breakpoints and display source code.

### 3. Open the workspace in VS Code

```powershell
code ~\vsdbg-prototype-test
```

### 4. Create or copy launch.json

Create `.vscode/launch.json` in your workspace (or copy from `devops/dev-containers/vscode-templates/launch.json.prototype-test`):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Prototype: Attach vsdbg over SSH",
      "type": "coreclr",
      "request": "attach",
      "processName": "PrototypeTest",
      "pipeTransport": {
        "pipeCwd": "${workspaceRoot}",
        "pipeProgram": "ssh",
        "pipeArgs": [
          "your-actual-vm-hostname-or-ip",  // ← CHANGE THIS
          "-T"
        ],
        "debuggerPath": "/vsdbg/vsdbg",
        "quoteArgs": false
      },
      "sourceFileMap": {
        "/home/your-vm-user/vsdbg-prototype/PrototypeTest": "${workspaceRoot}/PrototypeTest"
      },
      "justMyCode": false,
      "requireExactSource": false
    }
  ]
}
```

**Edit these fields:**
- `"your-actual-vm-hostname-or-ip"` → your VM's hostname, alias, or IP address (from `~/.ssh/config` or direct IP)
- `"/home/your-vm-user/vsdbg-prototype/PrototypeTest"` → path where the app is running on the VM (use `echo ~` on the VM to verify)

**Note on paths:**
- `"debuggerPath": "/vsdbg/vsdbg"` this is the path **on the VM** where vsdbg was installed (step 4 of README.md)
- To verify: `ssh your-vm-hostname "ls -la /vsdbg/vsdbg"` should show the executable
- The sourceFileMap's left side is also the path **on the VM**, while the right side is your local workstation path

### 5. Test the connection

1. **Set a breakpoint** in `Program.cs`:
   - Click on line 9 (`DoWork(i);`) or line 16 (`Console.WriteLine(message);`)
   - A red dot should appear

2. **Start debugging:**
   - Press `F5` or select **Run → Start Debugging**
   - Select "Prototype: Attach vsdbg over SSH"
   - Watch Debug Console to see that SSH command is sent

3. **What happens:**
   - VS Code automatically initiates an SSH connection to your VM
   - On first connection, you may see: "The authenticity of host can't be established, are you sure you want to continue?" → Type `yes` and press Enter
   - vsdbg attaches to the running `PrototypeTest` process
   - Your breakpoint should hit within a few seconds
   - The debug panel shows the call stack, variables, etc.

4. **Verify debugging works:**
   - Step over a line (F10)
   - Inspect variables in the Variables panel
   - Step into the `DoWork()` method (F11)
   - Hover over variables to see their values

### 6. Troubleshooting

| Problem | Solution |
|---------|----------|
| **Debug session spins/hangs with no feedback** | **Common causes:**<br>• SSH keys not set up (passwordless auth required) — see [SSH-SETUP.md](SSH-SETUP.md)<br>• SSH connection is waiting for input (password or host confirmation). Enable verbose logging to see what's happening: Add `"logging": { "engineLogging": true, "trace": true }` to launch.json and check the Debug Console output.<br>• Wrong hostname or no network connectivity — verify with `ping vm-hostname`<br>• vsdbg path doesn't exist — verify with `ssh vm-hostname "ls -la /vsdbg/vsdbg"`<br>• Process already has a debugger attached — kill and restart the test app<br>• Test app not running in VM; must be running for remote connection.<br><br>**Quick test:** Run `ssh vm-hostname "echo success"` from PowerShell. If it prompts for a password or hangs, your SSH config is wrong. |
| "Could not establish connection to remote" | Check hostname is correct; try `ping your-vm-hostname` from PowerShell |
| "Permission denied (publickey)" | SSH keys not set up; see [SSH-SETUP.md](SSH-SETUP.md) |
| "Process not found" | Check process name matches; run `ssh vm-hostname "ps aux \| grep PrototypeTest"` |
| "Unable to attach" | vsdbg may not be installed on VM; verify with `ssh vm-hostname "ls -la /vsdbg/vsdbg"` |
| Source file path doesn't match | Edit `sourceFileMap` in launch.json; the path must match the VM's actual directory |
| "Breakpoint not hit" | Add `"logging": { "engineLogging": true }` to launch config to see debug diagnostics |

#### Debugging a Spinning/Hanging Debug Session

If VS Code shows a spinning indicator with no feedback after pressing F5, follow these steps:

**Step 1: Enable verbose logging**

Edit your launch.json to add logging:
```json
{
  "name": "Prototype: Attach vsdbg over SSH",
  "type": "coreclr",
  "request": "attach",
  "processName": "PrototypeTest",
  "logging": {
    "engineLogging": true,
    "trace": true
  },
  "pipeTransport": {
    // ... rest of config
  }
}
```

**Step 2: Check the Debug Console**

Press `Ctrl+Shift+Y` to open the Debug Console. Look for output like:
- `Starting: "ssh" with arguments "vm-hostname -T"` — SSH command being executed
- `Waiting for /vsdbg/vsdbg to initialize` — vsdbg is being invoked
- Any error messages or where it gets stuck

**Step 3: Test SSH manually**

Open PowerShell and run:
```powershell
# This should complete immediately with no prompts
ssh your-vm-hostname "echo success"
```

If this:
- **Prompts for a password** → SSH keys not set up. See [SSH-SETUP.md](SSH-SETUP.md)
- **Asks "Are you sure you want to continue (yes/no)?"** → Run the command again and type `yes` to accept the host key
- **Hangs or times out** → Network connectivity issue. Check hostname/IP with `ping`
- **Shows "success" immediately** → SSH works; problem is elsewhere

**Step 4: Verify vsdbg exists**

```powershell
ssh your-vm-hostname "ls -la /vsdbg/vsdbg"
```

Should show the vsdbg executable. If "No such file or directory", install vsdbg:
```bash
curl -sSL https://aka.ms/getvsdbgsh | sudo bash /dev/stdin -v latest -l /vsdbg
```

**Step 5: Verify the test process is running**

```powershell
ssh your-vm-hostname "ps aux | grep PrototypeTest"
```

Should show the dotnet process. If not running, restart it on the VM:
```bash
cd ~/vsdbg-prototype/PrototypeTest
dotnet run -c Debug &
```

**Step 6: Check for port conflicts or existing debugger**

Only one debugger can attach to a process at a time. If you've tried multiple times:
```bash
# On VM - kill and restart
pkill -f PrototypeTest
dotnet run -c Debug --project ~/vsdbg-prototype/PrototypeTest/PrototypeTest.csproj &
```

**Common causes summary:**
- 90% of hangs are due to SSH waiting for password or host confirmation
- Ensure passwordless SSH works: `ssh vm-hostname "echo test"` should require no input
- Always check Debug Console output with verbose logging enabled

### 7. Clean up

When done testing, stop the process on the VM:

```bash
pkill -f PrototypeTest
rm -rf ~/vsdbg-prototype
```

## SSH Connection Behavior

When you press F5 to start debugging:

- VS Code **automatically initiates an SSH connection** using `ssh your-vm-hostname -T`
- The `-T` flag disables pseudo-terminal allocation (not needed for this)
- The SSH connection opens a pipe for communication with vsdbg
- The connection stays open for the duration of the debug session
- When you stop debugging (Shift+F5), the SSH connection closes

**You do NOT need to manually connect to the VM first.** The launch.json handles it automatically.

## What This Validates

✅ SSH authentication works (keys are set up correctly)
✅ vsdbg is installed and accessible on the VM
✅ The pipe transport mechanism works (vsdbg communicates via stdin/stdout)
✅ Source file mapping works (breakpoints resolve correctly)
✅ The same mechanism will work with `docker exec` in production

Once this prototype test passes, you're ready to wire up the containerized services.

## Next Steps

If this succeeds:
1. Return to [README.md](README.md) and proceed with step 6 (configure Dockerfiles)
2. The `launch.json.template` will use the same `pipeTransport` pattern, but with `docker exec` instead of direct SSH
3. When connected via Remote-SSH to the VM, `docker` commands will run locally and use the established SSH session

If this fails:
1. Check SSH keys (see [SSH-SETUP.md](SSH-SETUP.md))
2. Verify vsdbg installation: `ssh vm-hostname "ls /vsdbg/vsdbg"`
3. Verify .NET SDK: `ssh vm-hostname "dotnet --version"`
4. Check the VM can reach itself: `ssh vm-hostname "hostname"`
5. Enable verbose logging in launch.json: `"logging": { "engineLogging": true, "trace": "verbose" }`
