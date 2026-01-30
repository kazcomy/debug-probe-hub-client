# debug-probe-hub Client

This directory contains client tools for interacting with [debug-probe-hub](https://github.com/kazcomy/debug-probe-hub), a centralized debug probe server that provides remote firmware flashing and debugging capabilities.

## Overview

debug-probe-hub allows you to:
- Flash firmware to remote hardware via REST API
- Debug remotely via GDB port forwarding over SSH
- Share debug probes across multiple development machines
- Avoid USB/IP forwarding complications

## Files

- **client.py** - REST API client library
- **flash.py** - CLI tool for flashing firmware
- **gdb_tunnel.py** - SSH tunnel manager for remote debugging
- **requirements.txt** - Python dependencies

## Installation

```bash
# Install Python dependencies using apt (recommended for Debian/Ubuntu)
sudo apt-get install python3-requests

# Or using pip (if available)
pip install -r tool/debug-probe-hub-client/requirements.txt
```

## Configuration

Set the following environment variables (or use command-line arguments):

```bash
# debug-probe-hub server URL (API endpoint)
export DEBUG_PROBE_HUB_URL=http://192.168.1.100:8080

# SSH access to the debug-probe-hub server
export DEBUG_PROBE_HUB_SSH_HOST=192.168.1.100
export DEBUG_PROBE_HUB_SSH_USER=pi

# Default target and probe (optional)
export DEBUG_PROBE_HUB_TARGET=ch32v003
export DEBUG_PROBE_HUB_PROBE=4
```

Alternatively, create a `.env` file in the project root (see `.env.example`).

## Usage

### 1. List Available Probes

```bash
# Search for WCH-Link probes
./tool/debug-probe-hub-client/client.py search --interface wch-link

# List all probes
./tool/debug-probe-hub-client/client.py list-probes

# List supported targets
./tool/debug-probe-hub-client/client.py list-targets
```

### 2. Flash Firmware

```bash
# Flash with specific probe (recommended)
./tool/debug-probe-hub-client/flash.py \
  --target ch32v003 \
  --probe 4 \
  --firmware build/gfx_slave.bin

# Auto-detect compatible probe (requires server connection)
./tool/debug-probe-hub-client/flash.py --firmware build/gfx_slave.bin

# Using environment variables
export DEBUG_PROBE_HUB_PROBE=4
./tool/debug-probe-hub-client/flash.py --firmware build/gfx_slave.hex
```

**Important**: If you don't specify `--probe`, the script attempts to auto-detect a probe by querying the server. If the server is not accessible, you'll get:
```
Error: No compatible probe found. Please specify --probe.
```

Always use `--probe` or set `DEBUG_PROBE_HUB_PROBE` environment variable to avoid this issue.

**Via Makefile:**

```bash
# Set environment variables
export DEBUG_PROBE_HUB_PROBE=4

# Flash slave firmware
make flash-slave-remote

# Flash master firmware
make flash-master-remote
```

### 3. Debug with GDB

The `gdb_tunnel.py` script establishes an SSH tunnel and starts a debug session:

```bash
# Start GDB tunnel (keeps running until Ctrl+C)
./tool/debug-probe-hub-client/gdb_tunnel.py \
  --ssh-host 192.168.1.100 \
  --probe 4 \
  --local-port 3333
```

This will:
1. Call the debug-probe-hub API to start a debug session
2. Establish an SSH tunnel forwarding `localhost:3333` to the remote GDB server
3. Wait until interrupted (Ctrl+C)

**Connect GDB:**

```bash
# In another terminal
riscv-wch-elf-gdb build/gfx_slave.elf
(gdb) target remote localhost:3333
(gdb) monitor reset halt
(gdb) load
(gdb) continue
```

**Via VSCode:**

Use the VSCode debug configurations:
- "Debug Slave (Debug-Probe-Hub)"
- "Debug Master (Debug-Probe-Hub)"

These automatically start the SSH tunnel via VSCode tasks.

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG_PROBE_HUB_URL` | `http://remoteprogrammer.local.lan:8080` | API endpoint URL |
| `DEBUG_PROBE_HUB_SSH_HOST` | *(required)* | SSH hostname or IP |
| `DEBUG_PROBE_HUB_SSH_USER` | Current user | SSH username |
| `DEBUG_PROBE_HUB_TARGET` | `ch32v003` | Default target device |
| `DEBUG_PROBE_HUB_PROBE` | *(none)* | Default probe ID |

## API Client Library

You can also use `client.py` as a Python library:

```python
from tool.debug_probe_hub.client import DebugProbeHubClient

# Create client
client = DebugProbeHubClient(base_url="http://192.168.1.100:8080")

# Search for probes
probes = client.search_probes(interface="wch-link")
print(f"Found {len(probes)} probes")

# Flash firmware
result = client.flash_firmware(
    target="ch32v003",
    probe_id=4,
    firmware_path="build/gfx_slave.bin"
)

if result["status"] == "ok":
    print("Flash successful!")
```

## Submodule Usage

This directory is designed to be reusable across projects. You can:

1. **Copy to other projects:**
   ```bash
   cp -r tool/debug_probe_hub /path/to/other/project/tool/
   ```

2. **Convert to git submodule** (future):
   ```bash
   # After splitting into separate repository
   git submodule add https://github.com/kazcomy/debug-probe-hub-client.git tool/debug_probe_hub
   ```

## Troubleshooting

### Connection Errors

```
Error: Cannot connect to debug-probe-hub server
```

**Solutions:**
- Verify `DEBUG_PROBE_HUB_URL` is correct
- Check network connectivity: `curl http://192.168.1.100:8080/status`
- Ensure debug-probe-hub server is running

### SSH Tunnel Fails

```
Error: SSH tunnel failed to start
```

**Solutions:**
- Verify SSH access: `ssh user@host`
- Check `DEBUG_PROBE_HUB_SSH_HOST` and `DEBUG_PROBE_HUB_SSH_USER`
- Ensure SSH key authentication is set up (no password prompt)

### Probe Busy

```
Error: Probe #4 is busy
```

**Solutions:**
- Another user/session is using the probe
- Wait for the other session to finish
- Use a different probe: `--probe 5`

### Auto-detection Fails

```
Error: No compatible probe found. Please specify --probe.
Warning: Failed to auto-detect probe: ... Connection refused
```

**Cause:**
- debug-probe-hub server is not running or not accessible
- `DEBUG_PROBE_HUB_URL` is incorrect or not set
- Network connectivity issue

**Solutions:**

1. **Specify probe ID explicitly (recommended)**:
   ```bash
   export DEBUG_PROBE_HUB_PROBE=4
   ./tool/debug-probe-hub-client/flash.py --firmware build/gfx_slave.bin
   # or
   ./tool/debug-probe-hub-client/flash.py --probe 4 --firmware build/gfx_slave.bin
   ```

2. **Fix server connection** (if you need auto-detection):
   ```bash
   # Verify URL
   echo $DEBUG_PROBE_HUB_URL

   # Test connection
   curl http://192.168.1.100:8080/status

   # List available probes
   ./tool/debug-probe-hub-client/client.py list-probes
   ```

## Related Links

- [debug-probe-hub repository](https://github.com/kazcomy/debug-probe-hub)
- [debug-probe-hub setup guide](https://github.com/kazcomy/debug-probe-hub#setup)
