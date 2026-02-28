# debug-probe-hub Client

This directory contains client tools for interacting with [debug-probe-hub](https://github.com/kazcomy/debug-probe-hub), a centralized debug probe server that provides remote firmware flashing and debugging capabilities.

## Overview

debug-probe-hub allows you to:
- Flash firmware to remote hardware via REST API
- Debug remotely by connecting GDB directly over LAN
- Start print sessions (UART/RTT) via REST API
- Share debug probes across multiple development machines
- Avoid USB/IP forwarding complications

## Files

- **client.py** - REST API client library
- **flash.py** - CLI tool for flashing firmware
- **gdb_tunnel.py** - Debug session launcher (direct LAN endpoint output)
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

# Optional GDB endpoint overrides
export DEBUG_PROBE_HUB_GDB_HOST=192.168.1.100
export DEBUG_PROBE_HUB_GDB_BASE=3330

# Default target and probe (optional)
export DEBUG_PROBE_HUB_TARGET=ch32v003
export DEBUG_PROBE_HUB_PROBE=4
export DEBUG_PROBE_HUB_TRANSPORT=swd
export DEBUG_PROBE_HUB_PREFERRED_INTERFACE=wch-link
export DEBUG_PROBE_HUB_DEBUG_INTERFACE=jlink
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
  --target stm32g4 \
  --probe 1 \
  --transport swd \
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

The `gdb_tunnel.py` script starts a debug session and prints the direct GDB endpoint:

```bash
# Start debug server and print endpoint
./tool/debug-probe-hub-client/gdb_tunnel.py \
  --server http://192.168.1.100:8080 \
  --target stm32g4 \
  --probe 1 \
  --transport swd
```

Probe can also be auto-selected by target/mode compatibility:

```bash
./tool/debug-probe-hub-client/gdb_tunnel.py \
  --server http://192.168.1.100:8080 \
  --target stm32g4 \
  --preferred-interface jlink
```

This will:
1. Call the debug-probe-hub API to start a debug session
2. Resolve the direct endpoint (`<hub-host>:<gdb_base + probe_id>`)
3. Print connection target for GDB

If the session gets stuck or probe remains busy, force-stop it:

```bash
./tool/debug-probe-hub-client/client.py stop-session --probe 1 --kind all
```

### 4. Start UART/Print Session

Use the client command to start a print session on a dedicated probe:

```bash
./tool/debug-probe-hub-client/client.py \
  --server http://192.168.1.100:8080 \
  start-print \
  --target stm32g4 \
  --probe 10 \
  --baud 115200
```

Then connect to print TCP endpoint (`rtt_base + probe_id`, usually `9090 + probe_id`):

```bash
nc 192.168.1.100 9100
```

This lets you split probes:
- debug: `--probe 1` (J-Link)
- print: `--probe 10` (USB-UART)

**Connect GDB:**

```bash
# In another terminal
riscv-wch-elf-gdb build/gfx_slave.elf
(gdb) target remote 192.168.1.100:3331
(gdb) monitor reset halt
(gdb) load
(gdb) continue
```

**Via VSCode:**

Use the VSCode debug configurations:
- "Debug Slave (Debug-Probe-Hub)"
- "Debug Master (Debug-Probe-Hub)"

These should call `gdb_tunnel.py` before launching GDB, then connect directly to the printed endpoint.

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG_PROBE_HUB_URL` | `http://remoteprogrammer.local.lan:8080` | API endpoint URL |
| `DEBUG_PROBE_HUB_GDB_HOST` | *(derived from URL host)* | Optional GDB endpoint host override |
| `DEBUG_PROBE_HUB_GDB_BASE` | `3330` | Base GDB port for `probe_id -> port` calculation |
| `DEBUG_PROBE_HUB_TARGET` | `ch32v003` | Default target device |
| `DEBUG_PROBE_HUB_PROBE` | *(none)* | Default probe ID |
| `DEBUG_PROBE_HUB_TRANSPORT` | *(none)* | Optional transport (for example: `swd`, `jtag`) |
| `DEBUG_PROBE_HUB_PREFERRED_INTERFACE` | *(none)* | Preferred interface for flash auto probe selection |
| `DEBUG_PROBE_HUB_DEBUG_INTERFACE` | *(none)* | Preferred interface for debug auto probe selection |

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
    target="stm32g4",
    probe_id=1,
    firmware_path="build/gfx_slave.bin",
    transport="swd",
)

if result["status"] == "ok":
    print("Flash successful!")

# Start print session (UART/RTT)
client.start_print_session(target="stm32g4", probe_id=10, baud=115200)

# Force-release a probe lock when needed
client.stop_session(probe_id=1, kind="all")
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

### GDB Endpoint Unreachable

```
Error: GDB endpoint is not reachable yet
```

**Solutions:**
- Check probe session start log from `gdb_tunnel.py`
- Verify connectivity to hub: `nc -vz 192.168.1.100 3331`

### Probe Busy

```
Error: Probe #4 is busy
```

**Solutions:**
- Another user/session is using the probe
- Wait for the other session to finish
- Use a different probe: `--probe 5`
- Force release the probe session:
  `./tool/debug-probe-hub-client/client.py stop-session --probe 4 --kind all`

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
