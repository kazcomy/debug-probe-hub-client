#!/usr/bin/env python3
"""GDB session launcher for debug-probe-hub (direct LAN mode).

This script starts a debug session via the hub API and prints the direct
`host:port` endpoint for your GDB client.

Usage:
    ./gdb_tunnel.py --target stm32g4 --probe 1 --transport swd

Environment variables:
    DEBUG_PROBE_HUB_URL       API URL (default: http://remoteprogrammer.local.lan:8080)
    DEBUG_PROBE_HUB_GDB_HOST  Optional GDB host override
    DEBUG_PROBE_HUB_GDB_BASE  GDB base port (default: 3330)
    DEBUG_PROBE_HUB_TARGET    Default target name (default: ch32v003)
    DEBUG_PROBE_HUB_PROBE     Default probe ID
    DEBUG_PROBE_HUB_TRANSPORT Optional transport (e.g., swd, jtag)
"""

import argparse
import json
import os
import socket
import sys
import time
from typing import Optional
from urllib.parse import urlparse

try:
    from .client import DebugProbeHubClient
except ImportError:
    # Allow running as standalone script
    sys.path.insert(0, os.path.dirname(__file__))
    from client import DebugProbeHubClient

import requests


def format_http_error(error: requests.HTTPError) -> str:
    """Build a helpful message from HTTP error and response payload."""
    response = error.response
    if response is None:
        return str(error)

    details = []
    body_text = (response.text or "").strip()
    if body_text:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error_msg = payload.get("error")
                log_msg = payload.get("log")
                if error_msg:
                    details.append(str(error_msg).strip())
                if log_msg:
                    details.append(str(log_msg).strip())
        except (ValueError, json.JSONDecodeError):
            pass

        if not details:
            details.append(body_text)

    if details:
        return f"{error} | {' | '.join(details)}"
    return str(error)


def resolve_gdb_host(server_url: str, explicit_host: Optional[str]) -> str:
    """Resolve GDB host from explicit value or API URL hostname."""
    if explicit_host:
        return explicit_host
    parsed = urlparse(server_url)
    if parsed.hostname:
        return parsed.hostname
    return "localhost"


def wait_for_tcp_port(host: str, port: int, timeout_seconds: float) -> bool:
    """Wait until TCP port is reachable."""
    deadline = time.time() + max(timeout_seconds, 0.0)
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def start_debug_session(
    server_url: str,
    target: str,
    probe_id: int,
    transport: Optional[str],
    verbose: bool,
) -> bool:
    """Start debug session via API.

    Returns:
        True on success, False on failure.
    """
    try:
        client = DebugProbeHubClient(base_url=server_url)

        print("Starting debug session...", file=sys.stderr)
        print(f"  Target:    {target}", file=sys.stderr)
        print(f"  Probe ID:  {probe_id}", file=sys.stderr)
        if transport:
            print(f"  Transport: {transport}", file=sys.stderr)

        result = client.start_debug_session(
            target=target,
            probe_id=probe_id,
            transport=transport,
        )
        if result.get("status") != "ok":
            print("Failed to start debug session", file=sys.stderr)
            if "error" in result:
                print(f"Error: {result['error']}", file=sys.stderr)
            if "log" in result:
                print(result["log"], file=sys.stderr)
            return False

        log_text = result.get("log")
        if verbose and log_text:
            print("\nDebug output:", file=sys.stderr)
            print(log_text, file=sys.stderr)
        return True

    except requests.ConnectionError as e:
        print("Error: Cannot connect to debug-probe-hub API", file=sys.stderr)
        print(f"  URL: {server_url}", file=sys.stderr)
        print(f"  Details: {e}", file=sys.stderr)
        return False
    except requests.HTTPError as e:
        print("Error: debug-probe-hub rejected debug session request", file=sys.stderr)
        print(f"  Details: {format_http_error(e)}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error starting debug session: {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start remote debug session and print direct GDB endpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  DEBUG_PROBE_HUB_URL       API URL (default: http://remoteprogrammer.local.lan:8080)
  DEBUG_PROBE_HUB_GDB_HOST  Optional GDB host override
  DEBUG_PROBE_HUB_GDB_BASE  GDB base port (default: 3330)
  DEBUG_PROBE_HUB_TARGET    Default target name (default: ch32v003)
  DEBUG_PROBE_HUB_PROBE     Default probe ID
  DEBUG_PROBE_HUB_TRANSPORT Optional transport (e.g., swd, jtag)

Examples:
  %(prog)s --server http://remoteprogrammer.local.lan:8080 --target stm32g4 --probe 1 --transport swd
  %(prog)s --gdb-host 192.168.1.50 --target stm32g4 --probe 1
        """,
    )

    parser.add_argument(
        "--server",
        default=os.environ.get("DEBUG_PROBE_HUB_URL", "http://remoteprogrammer.local.lan:8080"),
        help="debug-probe-hub API URL",
    )
    parser.add_argument(
        "--gdb-host",
        default=os.environ.get("DEBUG_PROBE_HUB_GDB_HOST"),
        help="GDB host override (default: hostname from --server)",
    )
    parser.add_argument(
        "--gdb-base-port",
        type=int,
        default=int(os.environ.get("DEBUG_PROBE_HUB_GDB_BASE", "3330")),
        help="GDB base port used for probe->port calculation (default: 3330)",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=8.0,
        help="Seconds to wait for endpoint reachability check (default: 8.0, 0 to skip)",
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
        "--transport",
        default=os.environ.get("DEBUG_PROBE_HUB_TRANSPORT"),
        help="Transport selection (optional, e.g., swd, jtag)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.probe is None:
        print("Error: --probe is required (or set DEBUG_PROBE_HUB_PROBE)", file=sys.stderr)
        return 1

    started = start_debug_session(
        server_url=args.server,
        target=args.target,
        probe_id=args.probe,
        transport=args.transport,
        verbose=args.verbose,
    )
    if not started:
        return 1

    gdb_host = resolve_gdb_host(args.server, args.gdb_host)
    endpoint = f"{gdb_host}:{args.gdb_base_port + args.probe}"

    if args.wait_seconds > 0:
        print(
            f"Checking endpoint reachability (timeout: {args.wait_seconds:.1f}s)...",
            file=sys.stderr,
        )
        if not wait_for_tcp_port(gdb_host, args.gdb_base_port + args.probe, args.wait_seconds):
            print(
                f"Error: GDB endpoint is not reachable yet: {endpoint}",
                file=sys.stderr,
            )
            return 1

    print("Debug session ready", file=sys.stderr)
    print(f"  GDB endpoint: {endpoint}", file=sys.stderr)
    print("  Example: (gdb) target remote " + endpoint, file=sys.stderr)
    print(
        f"  Recovery: python3 client.py --server {args.server} stop-session --probe {args.probe} --kind all",
        file=sys.stderr,
    )
    print(endpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
