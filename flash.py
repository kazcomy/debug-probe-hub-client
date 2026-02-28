#!/usr/bin/env python3
"""CLI tool for flashing firmware via debug-probe-hub.

This script uploads firmware to a target device using debug-probe-hub's REST API.
It automatically searches for compatible probes if not specified.

Usage:
    ./flash.py --target stm32g4 --probe 1 --transport swd --firmware build/gfx_slave.bin
    ./flash.py --firmware build/gfx_slave.hex  # Auto-detect probe

Environment variables:
    DEBUG_PROBE_HUB_URL: Server URL (default: http://remoteprogrammer.local.lan:8080)
    DEBUG_PROBE_HUB_TARGET: Default target name (default: ch32v003)
    DEBUG_PROBE_HUB_PROBE: Default probe ID
    DEBUG_PROBE_HUB_TRANSPORT: Optional transport (e.g., swd, jtag)
    DEBUG_PROBE_HUB_PREFERRED_INTERFACE: Optional interface hint for auto probe selection
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

try:
    from .client import DebugProbeHubClient
except ImportError:
    # Allow running as standalone script
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from client import DebugProbeHubClient

import os
import requests


def find_compatible_probe(
    client: DebugProbeHubClient,
    target: str,
    preferred_interface: Optional[str] = None,
) -> Optional[int]:
    """Find a compatible probe for the target.

    Args:
        client: API client instance
        target: Target device name
        preferred_interface: Preferred interface type

    Returns:
        Probe ID if found, None otherwise
    """
    try:
        return client.find_compatible_probe(
            target=target,
            mode="flash",
            preferred_interface=preferred_interface,
        )

    except Exception as e:
        print(f"Warning: Failed to auto-detect probe: {e}", file=sys.stderr)

    return None


def flash_firmware(
    server: Optional[str],
    target: str,
    probe_id: Optional[int],
    firmware_path: str,
    transport: Optional[str] = None,
    preferred_interface: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """Flash firmware to target device.

    Args:
        server: debug-probe-hub server URL
        target: Target device name
        probe_id: Probe ID (None for auto-detect)
        firmware_path: Path to firmware file
        transport: Optional transport selection
        preferred_interface: Optional interface hint for auto probe selection
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    firmware_file = Path(firmware_path)
    if not firmware_file.exists():
        print(f"Error: Firmware file not found: {firmware_path}", file=sys.stderr)
        return 1

    try:
        client = DebugProbeHubClient(base_url=server)

        # Auto-detect probe if not specified
        if probe_id is None:
            print("Searching for compatible probe...", file=sys.stderr)
            probe_id = find_compatible_probe(
                client=client,
                target=target,
                preferred_interface=preferred_interface,
            )
            if probe_id is None:
                print(
                    "Error: No compatible probe found. Please specify --probe.",
                    file=sys.stderr,
                )
                return 1
            print(f"Found probe ID: {probe_id}", file=sys.stderr)

        # Display configuration
        print(f"Server:   {client.base_url}", file=sys.stderr)
        print(f"Target:   {target}", file=sys.stderr)
        print(f"Probe ID: {probe_id}", file=sys.stderr)
        if transport:
            print(f"Transport: {transport}", file=sys.stderr)
        if preferred_interface:
            print(f"Preferred interface: {preferred_interface}", file=sys.stderr)
        print(f"Firmware: {firmware_file.absolute()}", file=sys.stderr)
        print("", file=sys.stderr)

        # Flash firmware
        print("Flashing firmware...", file=sys.stderr)
        result = client.flash_firmware(
            target=target,
            probe_id=probe_id,
            firmware_path=str(firmware_file),
            transport=transport,
        )

        # Display result
        if result.get("status") == "ok":
            print("✓ Flash successful", file=sys.stderr)
            if verbose and "log" in result:
                print("\nOutput:", file=sys.stderr)
                print(result["log"])
            return 0
        else:
            print("✗ Flash failed", file=sys.stderr)
            if "error" in result:
                print(f"Error: {result['error']}", file=sys.stderr)
            if "log" in result:
                print("\nOutput:", file=sys.stderr)
                print(result["log"])
            return 1

    except requests.ConnectionError as e:
        print(f"Error: Cannot connect to debug-probe-hub server", file=sys.stderr)
        print(f"  URL: {server or os.environ.get('DEBUG_PROBE_HUB_URL', 'http://remoteprogrammer.local.lan:8080')}", file=sys.stderr)
        print(f"  Details: {e}", file=sys.stderr)
        return 1
    except requests.HTTPError as e:
        print(f"Error: HTTP error: {e}", file=sys.stderr)
        if hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Flash firmware via debug-probe-hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  DEBUG_PROBE_HUB_URL     Server URL (default: http://remoteprogrammer.local.lan:8080)
  DEBUG_PROBE_HUB_TARGET  Default target name (default: ch32v003)
  DEBUG_PROBE_HUB_PROBE   Default probe ID
  DEBUG_PROBE_HUB_TRANSPORT Optional transport (e.g., swd, jtag)
  DEBUG_PROBE_HUB_PREFERRED_INTERFACE Optional interface hint for auto probe selection

Examples:
  # Flash with specific probe
  %(prog)s --target stm32g4 --probe 1 --transport swd --firmware build/gfx_slave.bin

  # Auto-detect probe
  %(prog)s --firmware build/gfx_slave.hex

  # Use environment variables
  export DEBUG_PROBE_HUB_URL=http://192.168.1.100:8080
  export DEBUG_PROBE_HUB_PROBE=4
  %(prog)s --firmware build/gfx_slave.bin
        """,
    )

    parser.add_argument(
        "--server",
        help="debug-probe-hub server URL (default: $DEBUG_PROBE_HUB_URL)",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DEBUG_PROBE_HUB_TARGET", "ch32v003"),
        help="Target device name (default: $DEBUG_PROBE_HUB_TARGET or ch32v003)",
    )
    parser.add_argument(
        "--probe",
        type=int,
        default=os.environ.get("DEBUG_PROBE_HUB_PROBE"),
        help="Probe ID (default: auto-detect or $DEBUG_PROBE_HUB_PROBE)",
    )
    parser.add_argument(
        "--transport",
        default=os.environ.get("DEBUG_PROBE_HUB_TRANSPORT"),
        help="Transport selection (optional, e.g., swd, jtag)",
    )
    parser.add_argument(
        "--preferred-interface",
        default=os.environ.get("DEBUG_PROBE_HUB_PREFERRED_INTERFACE"),
        help="Preferred interface for auto probe selection (optional, e.g., jlink)",
    )
    parser.add_argument(
        "--firmware", required=True, help="Firmware file path (.bin, .hex, or .elf)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    return flash_firmware(
        server=args.server,
        target=args.target,
        probe_id=args.probe,
        firmware_path=args.firmware,
        transport=args.transport,
        preferred_interface=args.preferred_interface,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
