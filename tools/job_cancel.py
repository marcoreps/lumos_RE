#!/usr/bin/env python3
"""Cancels the current engraving job by means of

POST /process/control?action=2
"""

import argparse
import sys

import requests


DEFAULT_IP = "192.168.0.70"
DEFAULT_PORT = 8080
REQUEST_TIMEOUT = 10
ACTION = 2


def main():
    parser = argparse.ArgumentParser(description='Cancel the current engraving job (not yet live-tested on Lumos Ultra).')
    parser.add_argument(
        "--ip", default=DEFAULT_IP,
        help=f"Laser IP address (default: {DEFAULT_IP})",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"HTTP API port (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    url = f"http://{args.ip}:{args.port}/process/control"
    try:
        response = requests.post(
            url, params={"action": ACTION}, timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Unexpected non-JSON response: {response.text!r}") from exc
        if not isinstance(result, dict) or result.get("code") != 0 or result.get("result") != "ok":
            raise RuntimeError(f"Machine rejected cancel request: {result!r}")
    except (requests.RequestException, RuntimeError) as exc:
        print(f"Cancel request failed: {exc}", file=sys.stderr)
        return 1

    print("Cancel request accepted by the machine.")
    print("Verify actual machine behavior; HTTP success is not proof of motion state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
