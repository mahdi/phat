#!/usr/bin/env python3
"""Render cached Ookla Speedtest results on a red 212x104 Inky pHAT."""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inky_dashboard.paths import font_path, state_dir

WIDTH = 212
HEIGHT = 104
CACHE_PATH = state_dir() / "speedtest-cache.json"
LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "speedtest-logo.png"
DEFAULT_CACHE_MINUTES = 60
COMMAND_TIMEOUT_SECONDS = 100


@dataclass(frozen=True)
class SpeedResult:
    provider: str
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    tested_at: datetime


DEMO_RESULT = SpeedResult(
    provider="Hyperoptic Ltd",
    download_mbps=73.4,
    upload_mbps=31.8,
    ping_ms=5.2,
    tested_at=datetime.now().astimezone(),
)


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing timestamp")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def non_negative_number(value, name):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid {name}")
    return number


def parse_result(payload):
    try:
        provider = payload["isp"].strip()
        if not provider:
            raise ValueError("missing ISP")
        # Ookla's machine-readable formats report bandwidth in bytes per second.
        download = non_negative_number(payload["download"]["bandwidth"], "download")
        upload = non_negative_number(payload["upload"]["bandwidth"], "upload")
        ping = non_negative_number(payload["ping"]["latency"], "ping")
        tested_at = parse_timestamp(payload["timestamp"])
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Speedtest returned an unexpected result") from exc

    return SpeedResult(
        provider=provider,
        download_mbps=download / 125_000,
        upload_mbps=upload / 125_000,
        ping_ms=ping,
        tested_at=tested_at,
    )


def load_cached_result(cache_path=CACHE_PATH):
    try:
        payload = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        return parse_result(payload)
    except (OSError, json.JSONDecodeError, RuntimeError):
        return None


def save_cached_payload(payload, cache_path=CACHE_PATH):
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(cache_path)


def cache_is_fresh(result, max_age_minutes, now=None):
    if result is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - result.tested_at.astimezone(timezone.utc)
    return age <= timedelta(minutes=max(0, max_age_minutes))


def fetch_result():
    executable = os.environ.get("INKY_SPEEDTEST_BIN") or shutil.which("speedtest")
    if not executable:
        raise RuntimeError("Ookla Speedtest CLI is not installed")

    completed = subprocess.run(
        [executable, "--format=json", "--progress=no"],
        capture_output=True,
        check=False,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        message = detail[-1] if detail else f"exit code {completed.returncode}"
        raise RuntimeError(f"Speedtest failed: {message}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Speedtest did not return JSON") from exc
    return parse_result(payload), payload


def get_result(cache_path=CACHE_PATH, max_age_minutes=DEFAULT_CACHE_MINUTES):
    cached = load_cached_result(cache_path)
    if cache_is_fresh(cached, max_age_minutes):
        return cached, False

    try:
        result, payload = fetch_result()
        save_cached_payload(payload, cache_path)
        return result, False
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        if cached is not None:
            return cached, True
        raise


def fitted_text(draw, text, text_font, max_width):
    text = text.upper()
    if draw.textlength(text, font=text_font) <= max_width:
        return text
    ellipsis = "…"
    while text and draw.textlength(text + ellipsis, font=text_font) > max_width:
        text = text[:-1]
    return text + ellipsis


def right_aligned(draw, x, y, text, fill, text_font):
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text((x - (box[2] - box[0]), y), text, fill=fill, font=text_font)


def logo_mask(asset_path=LOGO_PATH):
    source = Image.open(asset_path).convert("RGBA")
    mask = source.getchannel("A")
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError(f"Speedtest logo contains no visible artwork: {asset_path}")
    mask = mask.crop(bounds)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    mask.thumbnail((108, 14), resampling)
    return mask.point(lambda value: 255 if value >= 80 else 0)


def format_speed(value):
    return f"{value:.1f}" if value < 100 else f"{value:.0f}"


def draw_arrow(draw, x, y, upward, colour):
    if upward:
        draw.polygon(
            (
                (x + 5, y),
                (x, y + 6),
                (x + 3, y + 6),
                (x + 3, y + 13),
                (x + 7, y + 13),
                (x + 7, y + 6),
                (x + 10, y + 6),
            ),
            fill=colour,
        )
    else:
        draw.polygon(
            (
                (x + 3, y),
                (x + 7, y),
                (x + 7, y + 7),
                (x + 10, y + 7),
                (x + 5, y + 13),
                (x, y + 7),
                (x + 3, y + 7),
            ),
            fill=colour,
        )


def draw_speed(draw, x, label, value, upward, black, accent, label_font, value_font):
    draw_arrow(draw, x, 26, upward, accent)
    draw.text((x + 15, 25), label, fill=accent, font=label_font)
    draw.text((x, 39), format_speed(value), fill=black, font=value_font)
    draw.text((x + 1, 68), "MBPS", fill=black, font=label_font)


def render(result, stale=False, preview=False):
    if preview:
        white, black, accent = (255, 255, 255), (0, 0, 0), (190, 0, 0)
        image = Image.new("RGB", (WIDTH, HEIGHT), white)
        display = None
    else:
        from inky import InkyPHAT

        display = InkyPHAT("red")
        display.set_border(display.BLACK)
        white, black, accent = display.WHITE, display.BLACK, display.RED
        image = Image.new("P", (display.WIDTH, display.HEIGHT), white)

    draw = ImageDraw.Draw(image)
    provider_font = ImageFont.truetype(str(font_path()), 9)
    label_font = ImageFont.truetype(str(font_path()), 8)
    value_font = ImageFont.truetype(str(font_path()), 28)
    footer_font = ImageFont.truetype(str(font_path()), 8)

    draw.rectangle((0, 0, WIDTH - 1, 19), fill=accent)
    logo = logo_mask()
    image.paste(white, (5, (20 - logo.height) // 2), logo)
    provider = fitted_text(draw, result.provider, provider_font, 88)
    right_aligned(draw, WIDTH - 5, 4, provider, white, provider_font)

    draw_speed(
        draw, 7, "DOWNLOAD", result.download_mbps, False, black, accent, label_font, value_font
    )
    draw.line((105, 24, 105, 75), fill=accent, width=1)
    draw_speed(draw, 113, "UPLOAD", result.upload_mbps, True, black, accent, label_font, value_font)

    draw.line((5, 78, WIDTH - 5, 78), fill=black)
    ping_text = f"PING {result.ping_ms:.0f} MS"
    tested_text = result.tested_at.astimezone().strftime("TESTED %H:%M")
    draw.text((5, 83), ping_text, fill=black, font=footer_font)
    right_aligned(draw, WIDTH - 5, 83, tested_text, black, footer_font)
    draw.text((5, 94), "PI WI-FI", fill=accent, font=footer_font)
    if stale:
        right_aligned(draw, WIDTH - 5, 94, "LAST RESULT", accent, footer_font)

    return image, display


def configured_cache_minutes():
    try:
        return max(0, int(os.environ.get("INKY_SPEEDTEST_CACHE_MINUTES", DEFAULT_CACHE_MINUTES)))
    except ValueError as exc:
        raise RuntimeError("INKY_SPEEDTEST_CACHE_MINUTES must be an integer") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preview",
        type=Path,
        help="write a PNG preview instead of refreshing the physical display",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use sample data for a preview without running a bandwidth test",
    )
    args = parser.parse_args()
    if args.demo and args.preview is None:
        parser.error("--demo requires --preview")

    try:
        result, stale = (
            (DEMO_RESULT, False)
            if args.demo
            else get_result(max_age_minutes=configured_cache_minutes())
        )
        image, display = render(result, stale=stale, preview=args.preview is not None)
        if args.preview:
            image.save(args.preview)
            print(f"Preview written to {args.preview}")
        else:
            display.set_image(image)
            display.show()
            print("Internet speed dashboard refreshed successfully")
        return 0
    except Exception as exc:
        print(f"Internet speed dashboard update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
