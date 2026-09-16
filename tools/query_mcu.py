#!/usr/bin/env python3
"""
Send commands to Lumos Ultras mcu1 through HTTP "API".

Examples:
    ./query_mcu.py M27
    ./query_mcu.py M43S0
"""

import argparse
import hashlib
import json
import sys

import requests


DEFAULT_IP = "192.168.0.70"
DEFAULT_PORT = 8080
DEFAULT_TIMEOUT = 10


def send_mcu_command(command, ip=DEFAULT_IP, port=DEFAULT_PORT,
                     timeout=DEFAULT_TIMEOUT, verbose=False):
    """Send a command to mcu1 and return response."""

    command = command.strip()

    if not command:
        raise ValueError("Command can't be empty")

    payload = f"{command}\n".encode("utf-8")
    md5_hash = hashlib.md5(payload).hexdigest().upper()

    endpoint = f"http://{ip}:{port}/test/cmd/mcu"

    if verbose:
        print(f"Endpoint : {endpoint}", file=sys.stderr)
        print(f"Command  : {command!r}", file=sys.stderr)
        print(f"Payload  : {payload!r}", file=sys.stderr)
        print(f"MD5      : {md5_hash}", file=sys.stderr)

    response = requests.post(
        endpoint,
        params={"md5": md5_hash},
        data=payload,
        timeout=timeout,
    )

    response.raise_for_status()

    try:
        result = response.json()
    except requests.exceptions.JSONDecodeError:
        raise RuntimeError(
            f"Device returned non-JSON response: {response.text!r}"
        )

    if verbose:
        print(
            "HTTP response:",
            json.dumps(result, indent=2),
            file=sys.stderr,
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Send a command to the WeCreat Lumos MCU."
    )

    parser.add_argument(
        "command",
        nargs="+",
        help="MCU/G-code command to send, e.g. M27, M43S0'",
    )

    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
        help=f"Laser IP address (default: {DEFAULT_IP})",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"HTTP API port (default: {DEFAULT_PORT})",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show request details and the complete JSON response",
    )

    args = parser.parse_args()

    # allows query_mcu.py G1 X10 Y20
    command = " ".join(args.command)

    try:
        result = send_mcu_command(
            command,
            ip=args.ip,
            port=args.port,
            timeout=args.timeout,
            verbose=args.verbose,
        )

    except requests.exceptions.RequestException as exc:
        print(f"Communication error: {exc}", file=sys.stderr)
        return 1

    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    data = result.get("data")

    if data not in (None, ""):
        print(data)

    code = result.get("code")
    if code not in (None, 0):
        if not args.verbose:
            print(
                f"Device returned API error code {code}: "
                f"{result.get('result', '')}",
                file=sys.stderr,
            )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())