#!/usr/bin/env python3
"""GDB tunnel manager for debug-probe-hub.

This script establishes an SSH tunnel to the debug-probe-hub server, starts a debug
session, and forwards the GDB port to localhost for use with VSCode or other GDB clients.

Usage:
    ./gdb_tunnel.py --target ch32v003 --probe 4 --local-port 3333

Environment variables:
    DEBUG_PROBE_HUB_URL       API URL (default: http://remoteprogrammer.local.lan:8080)
    DEBUG_PROBE_HUB_SSH_HOST  SSH hostname or IP (required)
    DEBUG_PROBE_HUB_SSH_USER  SSH username (default: current user)
    DEBUG_PROBE_HUB_TARGET    Default target name (default: ch32v003)
    DEBUG_PROBE_HUB_PROBE     Default probe ID
"""

import sys
import argparse
import os
import subprocess
import signal
import time
import shutil
import getpass
from typing import Optional

try:
    from .client import DebugProbeHubClient
except ImportError:
    # Allow running as standalone script
    sys.path.insert(0, os.path.dirname(__file__))
    from client import DebugProbeHubClient

import requests


def start_debug_session(
    server_url: str, target: str, probe_id: int, verbose: bool = False
) -> int:
    """Start debug session via API.

    Args:
        server_url: debug-probe-hub API URL
        target: Target device name
        probe_id: Probe ID
        verbose: Enable verbose output

    Returns:
        Remote GDB port number (0 on error)
    """
    try:
        client = DebugProbeHubClient(base_url=server_url)

        print(f"Starting debug session...", file=sys.stderr)
        print(f"  Target:   {target}", file=sys.stderr)
        print(f"  Probe ID: {probe_id}", file=sys.stderr)

        result = client.start_debug_session(target, probe_id)

        if result.get("status") == "ok":
            # Calculate GDB port
            gdb_port = client.get_gdb_port(probe_id)
            print(f"✓ Debug session started", file=sys.stderr)
            print(f"  Remote GDB port: {gdb_port}", file=sys.stderr)

            if verbose and "log" in result:
                print("\nDebug output:", file=sys.stderr)
                print(result["log"])

            return gdb_port
        else:
            print("✗ Failed to start debug session", file=sys.stderr)
            if "error" in result:
                print(f"Error: {result['error']}", file=sys.stderr)
            if "log" in result:
                print(f"Output: {result['log']}", file=sys.stderr)
            return 0

    except requests.ConnectionError as e:
        print(f"Error: Cannot connect to debug-probe-hub API", file=sys.stderr)
        print(f"  URL: {server_url}", file=sys.stderr)
        print(f"  Details: {e}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error starting debug session: {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        return 0


def establish_ssh_tunnel(
    ssh_host: str,
    ssh_user: str,
    local_port: int,
    remote_port: int,
    verbose: bool = False,
) -> Optional[subprocess.Popen]:
    """Establish SSH tunnel for GDB port forwarding.

    Args:
        ssh_host: SSH hostname or IP
        ssh_user: SSH username
        local_port: Local port to forward to
        remote_port: Remote GDB port
        verbose: Enable verbose SSH output

    Returns:
        Popen object for the SSH process, or None on error
    """
    ssh_cmd = [
        "ssh",
        "-N",  # No remote command
        "-L", f"{local_port}:localhost:{remote_port}",  # Port forwarding
        f"{ssh_user}@{ssh_host}",
    ]

    if verbose:
        ssh_cmd.insert(1, "-vvv")

    print(f"Establishing SSH tunnel...", file=sys.stderr)
    print(f"  SSH host: {ssh_user}@{ssh_host}", file=sys.stderr)
    print(f"  Forward:  localhost:{local_port} -> localhost:{remote_port}", file=sys.stderr)

    try:
        # Check if ssh is available
        if not shutil.which("ssh"):
            print("Error: ssh command not found", file=sys.stderr)
            return None

        # Start SSH tunnel
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE if not verbose else None,
            stderr=subprocess.PIPE if not verbose else None,
        )

        # Give SSH a moment to establish the tunnel
        time.sleep(2)

        # Check if process is still running
        if proc.poll() is not None:
            print("Error: SSH tunnel failed to start", file=sys.stderr)
            if proc.stderr:
                stderr = proc.stderr.read().decode()
                print(f"SSH error: {stderr}", file=sys.stderr)
            return None

        print("✓ SSH tunnel established", file=sys.stderr)
        return proc

    except Exception as e:
        print(f"Error establishing SSH tunnel: {e}", file=sys.stderr)
        return None


def cleanup_tunnel(ssh_proc: Optional[subprocess.Popen]):
    """Clean up SSH tunnel process.

    Args:
        ssh_proc: SSH process to terminate
    """
    if ssh_proc and ssh_proc.poll() is None:
        print("\nClosing SSH tunnel...", file=sys.stderr)
        ssh_proc.terminate()
        try:
            ssh_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Force killing SSH tunnel...", file=sys.stderr)
            ssh_proc.kill()
        print("SSH tunnel closed", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Establish SSH tunnel to debug-probe-hub GDB server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  DEBUG_PROBE_HUB_URL       API URL (default: http://remoteprogrammer.local.lan:8080)
  DEBUG_PROBE_HUB_SSH_HOST  SSH hostname (required if --ssh-host not provided)
  DEBUG_PROBE_HUB_SSH_USER  SSH username (default: current user)
  DEBUG_PROBE_HUB_TARGET    Default target name (default: ch32v003)
  DEBUG_PROBE_HUB_PROBE     Default probe ID

Examples:
  # Basic usage
  %(prog)s --ssh-host 192.168.1.100 --probe 4

  # Use environment variables
  export DEBUG_PROBE_HUB_SSH_HOST=192.168.1.100
  export DEBUG_PROBE_HUB_PROBE=4
  %(prog)s

  # Custom local port
  %(prog)s --ssh-host pi.local --probe 4 --local-port 3334
        """,
    )

    parser.add_argument(
        "--server",
        default=os.environ.get("DEBUG_PROBE_HUB_URL", "http://remoteprogrammer.local.lan:8080"),
        help="debug-probe-hub API URL (accessed via SSH tunnel, default: http://remoteprogrammer.local.lan:8080)",
    )
    parser.add_argument(
        "--ssh-host",
        default=os.environ.get("DEBUG_PROBE_HUB_SSH_HOST"),
        help="SSH hostname or IP (required, or set $DEBUG_PROBE_HUB_SSH_HOST)",
    )
    parser.add_argument(
        "--ssh-user",
        default=os.environ.get("DEBUG_PROBE_HUB_SSH_USER", os.environ.get("USER", getpass.getuser())),
        help="SSH username (default: current user or $DEBUG_PROBE_HUB_SSH_USER)",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DEBUG_PROBE_HUB_TARGET", "ch32v003"),
        help="Target device name (default: ch32v003 or $DEBUG_PROBE_HUB_TARGET)",
    )
    parser.add_argument(
        "--probe",
        type=int,
        default=os.environ.get("DEBUG_PROBE_HUB_PROBE"),
        help="Probe ID (required, or set $DEBUG_PROBE_HUB_PROBE)",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=3333,
        help="Local GDB port to forward to (default: 3333)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.ssh_host:
        print("Error: --ssh-host is required (or set DEBUG_PROBE_HUB_SSH_HOST)", file=sys.stderr)
        return 1

    if args.probe is None:
        print("Error: --probe is required (or set DEBUG_PROBE_HUB_PROBE)", file=sys.stderr)
        return 1

    # Start debug session
    remote_gdb_port = start_debug_session(
        args.server, args.target, args.probe, args.verbose
    )

    if remote_gdb_port == 0:
        return 1

    # Establish SSH tunnel
    ssh_proc = establish_ssh_tunnel(
        args.ssh_host,
        args.ssh_user,
        args.local_port,
        remote_gdb_port,
        args.verbose,
    )

    if not ssh_proc:
        return 1

    # Set up signal handlers for clean exit
    def signal_handler(sig, frame):
        cleanup_tunnel(ssh_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"\n✓ GDB tunnel ready", file=sys.stderr)
    print(f"  Connect GDB to: localhost:{args.local_port}", file=sys.stderr)
    print(f"  Press Ctrl+C to stop\n", file=sys.stderr)

    # Wait for SSH process to exit (or user interrupt)
    try:
        ssh_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_tunnel(ssh_proc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
