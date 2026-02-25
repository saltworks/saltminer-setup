# SSH Setup for Remote Debugging

This document explains how to configure SSH authentication for the remote debugging environment.

## Overview

The vsdbg pipe transport method requires SSH access from your workstation to the Ubuntu VM. VS Code uses SSH to:
1. Connect via Remote-SSH extension to browse/edit source code
2. Execute `docker` commands on the VM to invoke vsdbg inside containers
3. Forward ports for the Flask API dashboard and Vite dev server

## Option 1: SSH Key-Based Authentication (Recommended)

Key-based authentication is passwordless, secure, and required for AI agent automation.

### Windows Workstation Setup

1. **Generate an SSH key pair** (if you don't have one):
   ```powershell
   ssh-keygen -t ed25519 -C "your-email@example.com"
   ```
   
   - Press Enter to accept default location (`C:\Users\YourName\.ssh\id_ed25519`)
   - Optionally set a passphrase (you can use `ssh-agent` to cache it)

2. **Copy your public key to the VM:**
   ```powershell
   # Get your public key content
   Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
   
   # SSH to the VM and append it to authorized_keys
   ssh username@vm-hostname-or-ip "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
   # Then paste the public key and press Ctrl+D
   ```

   Or use `ssh-copy-id` if available (via Git Bash or WSL):
   ```bash
   ssh-copy-id username@vm-hostname-or-ip
   ```

3. **Test passwordless login:**
   ```powershell
   ssh username@vm-hostname-or-ip "echo Successfully connected"
   ```
   
   If this prompts for a password, your key wasn't copied correctly.

4. **Create or edit SSH config** (`C:\Users\YourName\.ssh\config`):
   ```
   Host vm1
       HostName 10.9.110.115
       User saltminer
       IdentityFile ~/.ssh/id_ed25519
       ForwardAgent yes
       ServerAliveInterval 60
       ServerAliveCountMax 3
   ```

   Now you can connect with just: `ssh vm1`

5. **Verify in VS Code:**
   - Install the "Remote - SSH" extension
   - Press `F1` → "Remote-SSH: Connect to Host"
   - Select `vm1` (or type `username@vm-hostname`)
   - Should connect without password prompt

### Ubuntu VM Setup

1. **Ensure SSH server is running:**
   ```bash
   sudo systemctl status ssh
   # If not running:
   sudo systemctl enable --now ssh
   ```

2. **Verify permissions on authorized_keys:**
   ```bash
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```

3. **Optional: Disable password authentication** (more secure):
   ```bash
   sudo nano /etc/ssh/sshd_config
   ```
   
   Set:
   ```
   PasswordAuthentication no
   PubkeyAuthentication yes
   ```
   
   Restart SSH:
   ```bash
   sudo systemctl restart ssh
   ```

## Option 2: Password Authentication (Not Recommended)

Password authentication works but has significant drawbacks:
- Interrupts debugging workflow with password prompts
- Not suitable for AI agent automation
- Less secure

### If You Must Use Passwords

1. **Enable password authentication on VM** (`/etc/ssh/sshd_config`):
   ```
   PasswordAuthentication yes
   ```

2. **In VS Code, enable login terminal** (`settings.json`):
   ```json
   {
     "remote.SSH.showLoginTerminal": true
   }
   ```

3. **Use ssh-agent to cache credentials** (reduces prompts):
   ```powershell
   # Start ssh-agent
   Start-Service ssh-agent
   Set-Service ssh-agent -StartupType Automatic
   
   # Add your key with passphrase
   ssh-add $env:USERPROFILE\.ssh\id_ed25519
   ```

> **Note:** Even with ssh-agent, some operations may still prompt for passwords. Key-based auth with passwordless keys is strongly recommended.

## Troubleshooting

### "Permission denied (publickey)"
- Your public key isn't in `~/.ssh/authorized_keys` on the VM
- Permissions are wrong: run `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`
- Wrong username in SSH config

### "Connection refused"
- SSH server not running on VM: `sudo systemctl start ssh`
- Firewall blocking port 22: `sudo ufw allow ssh`
- Wrong hostname or IP address

### "Could not establish connection to remote"
- Check SSH config syntax: `ssh -G saltminer-dev` (shows parsed config)
- Try verbose mode: `ssh -v username@vm-hostname`
- Ensure VS Code Remote-SSH extension is installed

### VS Code keeps prompting for password
- Key-based auth not set up correctly
- Passphrase on private key but ssh-agent not running
- Multiple SSH keys exist and wrong one is being used (specify with `IdentityFile`)

### vsdbg can't attach to process
- This is not an SSH issue - see debugging section in main README
- Verify you can run `docker ps` on the VM successfully

## Port Forwarding for Browser Access

VS Code Remote-SSH automatically forwards ports, but you can also configure defaults:

**In workspace `.vscode/settings.json`:**
```json
{
  "remote.SSH.defaultForwardedPorts": [
    { "localPort": 8080, "remotePort": 8080, "name": "Flask API Dashboard" },
    { "localPort": 5173, "remotePort": 5173, "name": "Vite Dev Server" },
    { "localPort": 5601, "remotePort": 5601, "name": "Kibana" }
  ]
}
```

Or manually forward in VS Code:
- `F1` → "Forward a Port" → Enter port number

Access forwarded services at `http://localhost:<port>` in your workstation browser.

## Security Best Practices

1. **Always use key-based authentication** for production or shared VMs
2. **Use passphrases on private keys** and let ssh-agent cache them
3. **Disable password authentication** on the VM once keys are set up
4. **Use SSH config aliases** instead of remembering IPs
5. **Set `ServerAliveInterval`** to prevent connection timeouts during debugging
6. **Don't share private keys** - each developer should have their own keypair
7. **Rotate keys periodically** and remove old keys from `authorized_keys`

## Further Reading

- [VS Code Remote Development over SSH](https://code.visualstudio.com/docs/remote/ssh)
- [OpenSSH Key Management](https://www.ssh.com/academy/ssh/keygen)
- [GitHub SSH Setup Guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh) (similar process)
