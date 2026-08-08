#!/usr/bin/env python3
"""Display the next enabled widget from a JSON rotation list."""

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from inky_dashboard.paths import state_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "widgets.json"


def load_widgets(config_path):
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    widgets = payload.get("widgets")
    if not isinstance(widgets, list):
        raise ValueError("widgets.json must contain a 'widgets' list")

    enabled = []
    seen_ids = set()
    for widget in widgets:
        if not isinstance(widget, dict):
            raise ValueError("Every widget entry must be a JSON object")
        widget_id = widget.get("id")
        command = widget.get("command")
        if not isinstance(widget_id, str) or not widget_id:
            raise ValueError("Every widget needs a non-empty string id")
        if widget_id in seen_ids:
            raise ValueError(f"Duplicate widget id: {widget_id}")
        seen_ids.add(widget_id)
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part for part in command)
        ):
            raise ValueError(f"Widget {widget_id!r} needs a command string list")
        if widget.get("enabled", True):
            enabled.append(widget)

    if not enabled:
        raise ValueError("At least one widget must be enabled")
    return enabled


def load_last_widget(state_path):
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
        return state.get("last_widget")
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return None


def select_next(widgets, last_widget):
    ids = [widget["id"] for widget in widgets]
    if last_widget not in ids:
        return widgets[0]
    return widgets[(ids.index(last_widget) + 1) % len(widgets)]


def expand(value):
    return value.format(python=sys.executable, project_root=str(PROJECT_ROOT))


def expanded_command(widget):
    return [expand(part) for part in widget["command"]]


def save_state(state_path, widget_id):
    state_path = Path(state_path)
    state = {
        "last_widget": widget_id,
        "displayed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    temporary_path = state_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(state_path)


def run_once(config_path, runtime_dir, dry_run=False):
    runtime_dir = Path(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state_path = runtime_dir / "rotation-state.json"
    lock_path = runtime_dir / "rotation.lock"

    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A widget refresh is already running; skipping this turn")
            return 0

        widgets = load_widgets(config_path)
        widget = select_next(widgets, load_last_widget(state_path))
        widget_id = widget["id"]
        widget_name = widget.get("name", widget_id)
        command = expanded_command(widget)
        working_directory = expand(widget.get("working_directory", "{project_root}"))
        timeout = int(widget.get("timeout_seconds", 120))

        print(f"Displaying widget: {widget_name} ({widget_id})", flush=True)
        if dry_run:
            print("Command:", " ".join(command))
            return 0

        try:
            result = subprocess.run(
                command,
                cwd=working_directory,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"Widget {widget_id!r} exceeded its {timeout}s timeout", file=sys.stderr)
            return 1

        if result.returncode != 0:
            print(
                f"Widget {widget_id!r} failed with exit code {result.returncode}",
                file=sys.stderr,
            )
            return result.returncode

        save_state(state_path, widget_id)
        print(f"Rotation state advanced to: {widget_id}", flush=True)
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state-dir", type=Path, default=state_dir())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run_once(args.config, args.state_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
