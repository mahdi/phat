"""Runtime paths shared by dashboard widgets and the rotation controller."""

import os
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "inky-dashboard"
DEFAULT_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def state_dir():
    path = Path(os.environ.get("INKY_DASHBOARD_STATE_DIR", str(DEFAULT_STATE_DIR))).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def font_path(bold=True):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    configured_dir = Path(
        os.environ.get("INKY_DASHBOARD_FONT_DIR", str(DEFAULT_FONT_DIR))
    ).expanduser()
    path = configured_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Required font not found: {path}. Install the DejaVu font package "
            "or set INKY_DASHBOARD_FONT_DIR."
        )
    return path
