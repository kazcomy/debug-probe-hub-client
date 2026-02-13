#!/usr/bin/env python3
"""debug-probe-hub REST API client library.

This module provides a Python client for interacting with debug-probe-hub servers.
It can be used standalone or imported as a library for other tools.

Environment variables:
    DEBUG_PROBE_HUB_URL: Base URL of the debug-probe-hub server (default: http://remoteprogrammer.local.lan:8080)
"""

import os
import sys
import requests
import json
from typing import Optional, Dict, List, Any
from pathlib import Path


class DebugProbeHubClient:
    """Client for debug-probe-hub REST API."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 60):
        """Initialize the client.

        Args:
            base_url: Base URL of debug-probe-hub server (e.g., http://192.168.1.100:8080)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.environ.get(
            "DEBUG_PROBE_HUB_URL", "http://remoteprogrammer.local.lan:8080"
        )
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        """Construct full URL from path."""
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def search_probes(
        self,
        interface: Optional[str] = None,
        vendor_id: Optional[str] = None,
        product_id: Optional[str] = None,
        serial: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for probes matching criteria.

        Args:
            interface: Interface type (e.g., 'wch-link', 'cmsis-dap', 'jlink')
            vendor_id: USB vendor ID (hex string, e.g., '1a86')
            product_id: USB product ID (hex string, e.g., '8012')
            serial: Serial number
            name: Probe name

        Returns:
            List of matching probe dictionaries

        Raises:
            requests.RequestException: On connection or HTTP errors
        """
        params = {}
        if interface:
            params["interface"] = interface
        if vendor_id:
            params["vendor_id"] = vendor_id
        if product_id:
            params["product_id"] = product_id
        if serial:
            params["serial"] = serial
        if name:
            params["name"] = name

        response = self.session.get(
            self._url("/probes/search"), params=params, timeout=self.timeout
        )
        response.raise_for_status()
        result = response.json()

        # Handle API response format: {"query": ..., "matches": [...], "count": N}
        if isinstance(result, dict) and "matches" in result:
            return result["matches"]
        return result

    def list_probes(self) -> List[Dict[str, Any]]:
        """List all configured probes.

        Returns:
            List of all probe dictionaries

        Raises:
            requests.RequestException: On connection or HTTP errors
        """
        response = self.session.get(self._url("/probes"), timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "probes" in payload:
            return payload["probes"]
        return payload

    def list_targets(self) -> List[Dict[str, Any]]:
        """List all supported target devices.

        Returns:
            List of target dictionaries with name, description, and compatible interfaces

        Raises:
            requests.RequestException: On connection or HTTP errors
        """
        response = self.session.get(self._url("/targets"), timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()

        # Handle API response format: {"targets": {"name": {...}}}
        if isinstance(payload, dict) and "targets" in payload:
            targets = payload["targets"]
            if isinstance(targets, dict):
                return [{"name": name, **(cfg or {})} for name, cfg in targets.items()]
            if isinstance(targets, list):
                return targets
        return payload

    def get_status(self) -> Dict[str, Any]:
        """Get probe hub status.

        Returns:
            Status dictionary

        Raises:
            requests.RequestException: On connection or HTTP errors
        """
        response = self.session.get(self._url("/status"), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def flash_firmware(
        self,
        target: str,
        probe_id: int,
        firmware_path: str,
        transport: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Flash firmware to target device.

        Args:
            target: Target device name (e.g., 'ch32v003')
            probe_id: Probe ID to use
            firmware_path: Path to firmware binary file
            transport: Optional transport selection (e.g., 'swd', 'jtag')

        Returns:
            Response dictionary with 'status' and 'log' keys

        Raises:
            FileNotFoundError: If firmware file doesn't exist
            requests.RequestException: On connection or HTTP errors
        """
        firmware_file = Path(firmware_path)
        if not firmware_file.exists():
            raise FileNotFoundError(f"Firmware file not found: {firmware_path}")

        with open(firmware_file, "rb") as f:
            files = {"file": (firmware_file.name, f, "application/octet-stream")}
            data = {"target": target, "probe": str(probe_id), "mode": "flash"}
            if transport:
                data["transport"] = transport

            response = self.session.post(
                self._url("/dispatch"), data=data, files=files, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

    def start_debug_session(
        self,
        target: str,
        probe_id: int,
        transport: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a debug session (launches GDB server).

        Args:
            target: Target device name (e.g., 'ch32v003')
            probe_id: Probe ID to use
            transport: Optional transport selection (e.g., 'swd', 'jtag')

        Returns:
            Response dictionary with 'status' and 'log' keys

        Raises:
            requests.RequestException: On connection or HTTP errors
        """
        data = {"target": target, "probe": str(probe_id), "mode": "debug"}
        if transport:
            data["transport"] = transport

        response = self.session.post(
            self._url("/dispatch"), data=data, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def stop_session(self, probe_id: int, kind: str = "all") -> Dict[str, Any]:
        """Stop active session(s) for a probe and force lock release.

        Args:
            probe_id: Probe ID to stop session for
            kind: Session kind to stop: "debug", "print", or "all" (default)

        Returns:
            Response dictionary with 'status' and 'log' keys

        Raises:
            ValueError: If kind is invalid
            requests.RequestException: On connection or HTTP errors
        """
        normalized_kind = (kind or "all").strip().lower()
        if normalized_kind not in {"debug", "print", "all"}:
            raise ValueError("kind must be one of: debug, print, all")

        data = {"probe": str(probe_id), "kind": normalized_kind}
        response = self.session.post(
            self._url("/session/stop"), data=data, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_gdb_port(self, probe_id: int, base_port: int = 3330) -> int:
        """Calculate GDB port for a probe.

        The debug-probe-hub uses the formula: gdb_port = base_port + probe_id

        Args:
            probe_id: Probe ID
            base_port: Base GDB port (default: 3330)

        Returns:
            GDB port number
        """
        return base_port + probe_id


def main():
    """CLI interface for testing the client."""
    import argparse

    parser = argparse.ArgumentParser(description="debug-probe-hub CLI client")
    parser.add_argument(
        "--server",
        help="debug-probe-hub server URL (default: $DEBUG_PROBE_HUB_URL or http://remoteprogrammer.local.lan:8080)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # search command
    search_parser = subparsers.add_parser("search", help="Search for probes")
    search_parser.add_argument("--interface", help="Interface type (e.g., wch-link)")
    search_parser.add_argument("--vendor-id", help="USB vendor ID")
    search_parser.add_argument("--product-id", help="USB product ID")
    search_parser.add_argument("--serial", help="Serial number")
    search_parser.add_argument("--name", help="Probe name")

    # list-probes command
    subparsers.add_parser("list-probes", help="List all probes")

    # list-targets command
    subparsers.add_parser("list-targets", help="List all target devices")

    # status command
    subparsers.add_parser("status", help="Get hub status")

    # stop-session command
    stop_parser = subparsers.add_parser("stop-session", help="Stop active session and release probe lock")
    stop_parser.add_argument("--probe", type=int, required=True, help="Probe ID")
    stop_parser.add_argument(
        "--kind",
        choices=["debug", "print", "all"],
        default="all",
        help="Session kind to stop (default: all)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        client = DebugProbeHubClient(base_url=args.server)

        if args.command == "search":
            result = client.search_probes(
                interface=args.interface,
                vendor_id=args.vendor_id,
                product_id=args.product_id,
                serial=args.serial,
                name=args.name,
            )
        elif args.command == "list-probes":
            result = client.list_probes()
        elif args.command == "list-targets":
            result = client.list_targets()
        elif args.command == "status":
            result = client.get_status()
        elif args.command == "stop-session":
            result = client.stop_session(probe_id=args.probe, kind=args.kind)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1

        print(json.dumps(result, indent=2))
        return 0

    except requests.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        response = getattr(e, "response", None)
        if response is not None:
            try:
                print(json.dumps(response.json(), indent=2), file=sys.stderr)
            except Exception:
                if response.text:
                    print(response.text, file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
