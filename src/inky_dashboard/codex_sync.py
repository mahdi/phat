#!/usr/bin/env python3
"""Export a sanitized Codex rate-limit snapshot and optionally copy it to a Pi."""

import argparse
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

CLIENT_NAME = "inky_dashboard"
REQUEST_TIMEOUT_SECONDS = 20
SAFE_REMOTE_HOST = re.compile(r"^[A-Za-z0-9_.@-]+$")
SAFE_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9_./-]+$")


def window_label(minutes):
    labels = {
        60: "HOURLY",
        300: "5-HOUR",
        1440: "DAILY",
        10080: "WEEKLY",
        43200: "MONTHLY",
    }
    if minutes in labels:
        return labels[minutes]
    if minutes % 1440 == 0:
        return f"{minutes // 1440}-DAY"
    if minutes % 60 == 0:
        return f"{minutes // 60}-HOUR"
    return f"{minutes}-MIN"


def parse_percentage(value):
    number = float(value)
    if not 0 <= number <= 100:
        raise ValueError("usedPercent must be between 0 and 100")
    return number


def sanitized_window(payload, kind):
    minutes = int(payload["windowDurationMins"])
    if minutes <= 0:
        raise ValueError("windowDurationMins must be positive")
    used = parse_percentage(payload["usedPercent"])
    resets_at = datetime.fromtimestamp(int(payload["resetsAt"]), timezone.utc)
    return {
        "kind": kind,
        "label": window_label(minutes),
        "used_percent": used,
        "remaining_percent": max(0.0, 100.0 - used),
        "window_minutes": minutes,
        "resets_at": resets_at.isoformat(),
    }


def build_snapshot(result, now=None):
    limits = result.get("rateLimits")
    if not isinstance(limits, dict):
        raise ValueError("Codex returned no rate-limit information")

    windows = []
    for kind in ("primary", "secondary"):
        value = limits.get(kind)
        if isinstance(value, dict):
            windows.append(sanitized_window(value, kind))
    if not windows:
        raise ValueError("Codex returned no quota windows")

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    plan_type = limits.get("planType")
    return {
        "schema_version": 1,
        "updated_at": now.astimezone(timezone.utc).isoformat(),
        "plan_type": plan_type if isinstance(plan_type, str) else None,
        "limits": windows,
    }


def query_codex(codex_bin, timeout=REQUEST_TIMEOUT_SECONDS):
    process = subprocess.Popen(
        [codex_bin, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    selector = selectors.DefaultSelector()
    try:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Could not open Codex app-server pipes")
        selector.register(process.stdout, selectors.EVENT_READ)
        messages = [
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": CLIENT_NAME,
                        "title": "Inky Dashboard",
                        "version": "0.1.0",
                    }
                },
            },
            {"method": "initialized", "params": {}},
            {"method": "account/rateLimits/read", "id": 1},
        ]
        for message in messages:
            process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(remaining):
                break
            line = process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != 1:
                continue
            if "error" in message:
                raise RuntimeError(f"Codex rate-limit request failed: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Codex returned an invalid rate-limit response")
            return result

        detail = ""
        if process.stderr is not None and process.poll() is not None:
            detail = process.stderr.read().strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Timed out waiting for Codex rate limits{suffix}")
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def split_destination(destination):
    host, separator, path = destination.partition(":")
    if (
        not separator
        or not SAFE_REMOTE_HOST.fullmatch(host)
        or not SAFE_REMOTE_PATH.fullmatch(path)
    ):
        raise ValueError("destination must look like user@host:/absolute/safe/path.json")
    return host, path


def ssh_options(identity_file=None):
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if identity_file:
        options.extend(["-i", str(Path(identity_file).expanduser())])
    return options


def upload_snapshot(payload, destination, identity_file=None):
    host, remote_path = split_destination(destination)
    remote_temp = remote_path + ".tmp"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as temporary:
        json.dump(payload, temporary, indent=2)
        temporary.write("\n")
        temporary.flush()
        subprocess.run(
            ["scp", *ssh_options(identity_file), temporary.name, f"{host}:{remote_temp}"],
            check=True,
            timeout=30,
        )
    subprocess.run(
        ["ssh", *ssh_options(identity_file), host, "mv", remote_temp, remote_path],
        check=True,
        timeout=20,
    )


def write_snapshot(payload, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(output_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-bin",
        default=os.environ.get("INKY_CODEX_BIN") or shutil.which("codex"),
        help="path to the authenticated Codex CLI",
    )
    parser.add_argument("--output", type=Path, help="also write the sanitized snapshot locally")
    parser.add_argument(
        "--destination",
        help="optional scp destination, for example pi@raspberrypi.local:/path/usage.json",
    )
    parser.add_argument("--identity-file", type=Path, help="optional SSH private key")
    args = parser.parse_args()

    try:
        if not args.codex_bin:
            raise RuntimeError("Codex CLI was not found")
        snapshot = build_snapshot(query_codex(args.codex_bin))
        if args.output:
            write_snapshot(snapshot, args.output)
        if args.destination:
            upload_snapshot(snapshot, args.destination, args.identity_file)
        if not args.output and not args.destination:
            json.dump(snapshot, sys.stdout, indent=2)
            print()
        print("Codex usage snapshot refreshed", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"Codex usage sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
