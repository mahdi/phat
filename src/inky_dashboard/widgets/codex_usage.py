#!/usr/bin/env python3
"""Render a sanitized Codex usage snapshot on a red 212x104 Inky pHAT."""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inky_dashboard.paths import font_path, state_dir

WIDTH = 212
HEIGHT = 104
SNAPSHOT_PATH = state_dir() / "codex-usage.json"
LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "codex-logo.png"
STALE_AFTER_HOURS = 6


@dataclass(frozen=True)
class UsageWindow:
    label: str
    used_percent: float
    remaining_percent: float
    resets_at: datetime


@dataclass(frozen=True)
class UsageSnapshot:
    plan_type: str
    updated_at: datetime
    limits: tuple


DEMO_SNAPSHOT = UsageSnapshot(
    plan_type="plus",
    updated_at=datetime.now(timezone.utc),
    limits=(
        UsageWindow(
            label="WEEKLY",
            used_percent=10,
            remaining_percent=90,
            resets_at=datetime.now(timezone.utc) + timedelta(days=7),
        ),
    ),
)


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def percentage(value, name):
    number = float(value)
    if not 0 <= number <= 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return number


def parse_snapshot(payload):
    try:
        plan_type = payload.get("plan_type") or "CHATGPT"
        if not isinstance(plan_type, str):
            raise ValueError("invalid plan type")
        updated_at = parse_timestamp(payload["updated_at"])
        limits = []
        for item in payload["limits"]:
            label = item["label"].strip().upper()
            if not label:
                raise ValueError("missing limit label")
            limits.append(
                UsageWindow(
                    label=label,
                    used_percent=percentage(item["used_percent"], "used percent"),
                    remaining_percent=percentage(item["remaining_percent"], "remaining percent"),
                    resets_at=parse_timestamp(item["resets_at"]),
                )
            )
        if not limits:
            raise ValueError("missing usage limits")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Codex usage snapshot has an unexpected format") from exc
    return UsageSnapshot(plan_type=plan_type, updated_at=updated_at, limits=tuple(limits))


def load_snapshot(snapshot_path=SNAPSHOT_PATH):
    try:
        payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        return parse_snapshot(payload)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        raise RuntimeError("No valid Codex usage snapshot is available") from exc


def is_stale(snapshot, now=None, stale_after_hours=STALE_AFTER_HOURS):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - snapshot.updated_at.astimezone(timezone.utc)
    return age > timedelta(hours=stale_after_hours)


def right_aligned(draw, x, y, text, fill, text_font):
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text((x - (box[2] - box[0]), y), text, fill=fill, font=text_font)


def logo_masks(asset_path=LOGO_PATH):
    """Return display-safe masks for the Codex mark and its terminal glyph."""
    source = Image.open(asset_path).convert("RGBA")
    bounds = source.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"Codex logo contains no visible artwork: {asset_path}")
    source = source.crop(bounds)

    def is_glyph(pixel):
        red, green, blue, alpha = pixel
        channels = (red, green, blue)
        return alpha >= 80 and min(channels) >= 170 and max(channels) - min(channels) < 45

    silhouette = source.getchannel("A")
    glyph = Image.new("L", source.size)
    if hasattr(source, "get_flattened_data"):
        pixels = source.get_flattened_data()
    else:
        pixels = source.getdata()
    glyph.putdata([255 if is_glyph(pixel) else 0 for pixel in pixels])

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    silhouette.thumbnail((17, 17), resampling)
    glyph.thumbnail((17, 17), resampling)
    silhouette = silhouette.point(lambda value: 255 if value >= 64 else 0)
    glyph = glyph.point(lambda value: 255 if value >= 80 else 0)
    return silhouette, glyph


def draw_bar(draw, x, y, width, used_percent, black, accent):
    draw.rectangle((x, y, x + width, y + 9), outline=black)
    fill_width = round((width - 2) * used_percent / 100)
    if fill_width:
        draw.rectangle((x + 1, y + 1, x + fill_width, y + 8), fill=accent)


def reset_text(window):
    reset_at = window.resets_at.astimezone()
    return f"{reset_at:%a} {reset_at.day} {reset_at:%b}  {reset_at:%H:%M}".upper()


def draw_single_limit(draw, window, black, accent, fonts):
    label_font, percent_font, left_font, detail_font = fonts
    draw.text((6, 23), f"{window.label} LIMIT", fill=accent, font=label_font)
    remaining_text = f"{window.remaining_percent:.0f}%"
    remaining_colour = accent if window.remaining_percent <= 20 else black
    draw.text((6, 30), remaining_text, fill=remaining_colour, font=percent_font)
    box = draw.textbbox((6, 30), remaining_text, font=percent_font)
    draw.text((box[2] + 4, 47), "LEFT", fill=remaining_colour, font=left_font)
    right_aligned(
        draw,
        WIDTH - 6,
        48,
        f"USED {window.used_percent:.0f}%",
        accent,
        detail_font,
    )
    draw_bar(draw, 6, 69, WIDTH - 12, window.used_percent, black, accent)
    draw.text((6, 81), "NEXT RESET", fill=accent, font=detail_font)
    right_aligned(draw, WIDTH - 6, 81, reset_text(window), black, detail_font)


def draw_multiple_limits(draw, windows, black, accent, fonts):
    label_font, value_font, detail_font = fonts
    for index, window in enumerate(windows[:2]):
        y = 24 + index * 32
        draw.text((6, y), window.label, fill=accent, font=label_font)
        colour = accent if window.remaining_percent <= 20 else black
        right_aligned(
            draw,
            WIDTH - 6,
            y - 2,
            f"{window.remaining_percent:.0f}% LEFT",
            colour,
            value_font,
        )
        draw_bar(draw, 6, y + 13, WIDTH - 12, window.used_percent, black, accent)
        right_aligned(draw, WIDTH - 6, y + 22, f"RESET {reset_text(window)}", black, detail_font)


def render(snapshot, stale=False, preview=False):
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
    title_font = ImageFont.truetype(str(font_path()), 12)
    plan_font = ImageFont.truetype(str(font_path()), 9)
    label_font = ImageFont.truetype(str(font_path()), 8)
    percent_font = ImageFont.truetype(str(font_path()), 34)
    left_font = ImageFont.truetype(str(font_path()), 13)
    value_font = ImageFont.truetype(str(font_path()), 14)
    detail_font = ImageFont.truetype(str(font_path()), 8)
    footer_font = ImageFont.truetype(str(font_path()), 8)

    draw.rectangle((0, 0, WIDTH - 1, 19), fill=accent)
    silhouette, glyph = logo_masks()
    logo_position = (4, (20 - silhouette.height) // 2)
    image.paste(white, logo_position, silhouette)
    image.paste(accent, logo_position, glyph)
    draw.text((25, 2), "CODEX USAGE", fill=white, font=title_font)
    right_aligned(draw, WIDTH - 5, 4, snapshot.plan_type.upper(), white, plan_font)

    if len(snapshot.limits) == 1:
        draw_single_limit(
            draw,
            snapshot.limits[0],
            black,
            accent,
            (label_font, percent_font, left_font, detail_font),
        )
    else:
        draw_multiple_limits(
            draw,
            snapshot.limits,
            black,
            accent,
            (label_font, value_font, footer_font),
        )

    synced = snapshot.updated_at.astimezone().strftime("SYNCED %a %H:%M").upper()
    draw.text((5, 94), synced, fill=black, font=footer_font)
    right_aligned(
        draw,
        WIDTH - 5,
        94,
        "STALE" if stale else "CURRENT",
        accent if stale else black,
        footer_font,
    )
    return image, display


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
        help="use sample data for a preview",
    )
    args = parser.parse_args()
    if args.demo and args.preview is None:
        parser.error("--demo requires --preview")

    try:
        snapshot = DEMO_SNAPSHOT if args.demo else load_snapshot()
        stale = False if args.demo else is_stale(snapshot)
        image, display = render(snapshot, stale=stale, preview=args.preview is not None)
        if args.preview:
            image.save(args.preview)
            print(f"Preview written to {args.preview}")
        else:
            display.set_image(image)
            display.show()
            print("Codex usage dashboard refreshed successfully")
        return 0
    except Exception as exc:
        print(f"Codex usage dashboard update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
