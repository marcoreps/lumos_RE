#!/usr/bin/env python3
"""
Upload and start a firmware update on a WeCreat Lumos laser engraver.

Example:
    ./firmware_update.py firmware.tar.gz
"""

import argparse
import hashlib
import json
import sys

import requests


DEFAULT_IP = "192.168.0.70"
DEFAULT_PORT = 8080
UPLOAD_TIMEOUT = 120
START_TIMEOUT = 15


def md5_file(filename):
    """Return the uppercase MD5"""
    digest = hashlib.md5()

    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def check_response(response, operation):
    """Validate the response returned by the machine"""
    response.raise_for_status()

    try:
        result = response.json()
    except requests.exceptions.JSONDecodeError:
        raise RuntimeError(
            f"{operation} returned non-JSON data: {response.text!r}"
        )

    if result.get("code") != 0 or result.get("result") != "ok":
        raise RuntimeError(
            f"{operation} failed: {json.dumps(result)}"
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Upload and start a Lumos Ultra firmware update."
    )

    parser.add_argument(
        "firmware",
        help="Firmware update .tar.gz pack",
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
        "--upload-only",
        action="store_true",
        help="Upload and verify the archive without starting the update",
    )

    args = parser.parse_args()

    base_url = f"http://{args.ip}:{args.port}"

    try:
        md5_hash = md5_file(args.firmware)
    except OSError as exc:
        print(f"Cannot read firmware: {exc}", file=sys.stderr)
        return 1

    print(f"Firmware : {args.firmware}")
    print(f"MD5      : {md5_hash}")
    print(f"Device   : {args.ip}:{args.port}")

    upload_url = (
        f"{base_url}/ota/upload"
        f"?md5={md5_hash}&upgrade_type=0"
    )

    print("\nUploading firmware...")

    try:
        with open(args.firmware, "rb") as f:
            response = requests.post(
                upload_url,
                data=f,
                headers={"Content-Type": "application/octet-stream"},
                timeout=UPLOAD_TIMEOUT,
            )

        check_response(response, "Firmware upload")

    except (requests.RequestException, RuntimeError) as exc:
        print(f"Upload failed: {exc}", file=sys.stderr)
        return 1

    print("Upload accepted by device.")

    if args.upload_only:
        print("Upload-only mode: update has not been started.")
        return 0

    start_url = f"{base_url}/ota/start?upgrade_type=0"

    print("Starting firmware update...")

    try:
        response = requests.post(
            start_url,
            headers={
                "Content-Type":
                "application/x-www-form-urlencoded"
            },
            timeout=START_TIMEOUT,
        )

        check_response(response, "OTA start")

    except (requests.RequestException, RuntimeError) as exc:
        print(f"Could not start update: {exc}", file=sys.stderr)
        return 1

    print()
    print("Firmware update accepted. Don't disturb it for like a really really long time and then power cycle it. Good luck!")
    print()


    return 0


if __name__ == "__main__":
    sys.exit(main())