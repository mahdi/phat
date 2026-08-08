#!/usr/bin/env python3
"""Render Raspberry Pi health information on a red 212x104 Inky pHAT."""

import argparse
import os
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from inky_dashboard.paths import font_path

WIDTH = 212
HEIGHT = 104


@dataclass(frozen=True)
class HealthStats:
    hostname: str
    temperature_c: Optional[float]
    uptime_seconds: Optional[float]
    load_one: Optional[float]
    cpu_count: int
    memory_percent: Optional[float]
    disk_percent: Optional[float]
    wifi_dbm: Optional[float]
    ip_address: str


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def parse_meminfo(text):
    if not text:
        return None
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            try:
                values[key] = int(value.split()[0])
            except (IndexError, ValueError):
                continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return max(0.0, min(100.0, (total - available) / total * 100))


def parse_wifi_dbm(text):
    if not text:
        return None
    for line in text.splitlines():
        if ":" not in line:
            continue
        fields = line.replace(":", " ").split()
        if len(fields) >= 4:
            try:
                return float(fields[3].rstrip("."))
            except ValueError:
                continue
    return None


def local_ip():
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("8.8.8.8", 80))
        return connection.getsockname()[0]
    except OSError:
        return "OFFLINE"
    finally:
        connection.close()


def collect_health():
    temperature_text = read_text("/sys/class/thermal/thermal_zone0/temp")
    uptime_text = read_text("/proc/uptime")
    load_text = read_text("/proc/loadavg")

    try:
        temperature = float(temperature_text.strip()) / 1000 if temperature_text else None
    except ValueError:
        temperature = None
    try:
        uptime = float(uptime_text.split()[0]) if uptime_text else None
    except (IndexError, ValueError):
        uptime = None
    try:
        load = float(load_text.split()[0]) if load_text else None
    except (IndexError, ValueError):
        load = None

    try:
        disk = shutil.disk_usage("/")
        disk_percent = disk.used / disk.total * 100 if disk.total else None
    except OSError:
        disk_percent = None

    return HealthStats(
        hostname=socket.gethostname().split(".")[0].upper(),
        temperature_c=temperature,
        uptime_seconds=uptime,
        load_one=load,
        cpu_count=os.cpu_count() or 1,
        memory_percent=parse_meminfo(read_text("/proc/meminfo")),
        disk_percent=disk_percent,
        wifi_dbm=parse_wifi_dbm(read_text("/proc/net/wireless")),
        ip_address=local_ip(),
    )


def format_uptime(seconds):
    if seconds is None:
        return "UNKNOWN"
    total_minutes = max(0, int(seconds)) // 60
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    if days:
        return f"{days}D {hours}H"
    return f"{hours}H {minutes:02d}M"


def load_ratio(stats):
    if stats.load_one is None:
        return None
    return stats.load_one / max(1, stats.cpu_count)


def health_issues(stats):
    issues = []
    if stats.temperature_c is not None and stats.temperature_c >= 75:
        issues.append("temperature")
    if load_ratio(stats) is not None and load_ratio(stats) >= 1:
        issues.append("load")
    if stats.memory_percent is not None and stats.memory_percent >= 90:
        issues.append("memory")
    if stats.disk_percent is not None and stats.disk_percent >= 90:
        issues.append("disk")
    if stats.wifi_dbm is not None and stats.wifi_dbm <= -75:
        issues.append("wifi")
    return issues


def right_aligned(draw, x, y, text, fill, text_font):
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text((x - (box[2] - box[0]), y), text, fill=fill, font=text_font)


def draw_metric(
    draw,
    x,
    width,
    label,
    value,
    ratio,
    warning,
    black,
    accent,
    label_font,
    value_font,
):
    colour = accent if warning else black
    draw.text((x, 64), label, fill=accent, font=label_font)
    right_aligned(draw, x + width, 62, value, colour, value_font)
    draw.rectangle((x, 76, x + width, 82), outline=black)
    if ratio is not None:
        fill_width = round((width - 2) * max(0.0, min(1.0, ratio)))
        if fill_width:
            draw.rectangle((x + 1, 77, x + fill_width, 81), fill=colour)


def render(stats, preview=False):
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
    status_font = ImageFont.truetype(str(font_path()), 10)
    label_font = ImageFont.truetype(str(font_path()), 7)
    temperature_font = ImageFont.truetype(str(font_path()), 29)
    unit_font = ImageFont.truetype(str(font_path()), 12)
    uptime_font = ImageFont.truetype(str(font_path()), 15)
    detail_font = ImageFont.truetype(str(font_path(bold=False)), 7)
    metric_font = ImageFont.truetype(str(font_path()), 9)
    footer_font = ImageFont.truetype(str(font_path()), 8)

    issues = health_issues(stats)
    draw.rectangle((0, 0, WIDTH - 1, 19), fill=accent)
    draw.text((5, 2), "PI HEALTH", fill=white, font=title_font)
    right_aligned(draw, WIDTH - 5, 3, "CHECK" if issues else "GOOD", white, status_font)

    temperature_warning = "temperature" in issues
    temperature_colour = accent if temperature_warning else black
    temperature_text = "--" if stats.temperature_c is None else str(round(stats.temperature_c))
    draw.text((6, 22), temperature_text, fill=temperature_colour, font=temperature_font)
    temperature_box = draw.textbbox((6, 22), temperature_text, font=temperature_font)
    draw.text(
        (temperature_box[2] + 2, 27),
        "°C",
        fill=temperature_colour,
        font=unit_font,
    )
    draw.text((7, 50), "CPU TEMPERATURE", fill=accent, font=label_font)

    draw.line((107, 23, 107, 57), fill=accent, width=2)
    draw.text((115, 23), "UPTIME", fill=accent, font=label_font)
    draw.text((115, 32), format_uptime(stats.uptime_seconds), fill=black, font=uptime_font)
    draw.text((115, 51), stats.hostname[:15], fill=black, font=detail_font)

    draw.line((5, 60, WIDTH - 5, 60), fill=black)
    load_value = "--" if stats.load_one is None else f"{stats.load_one:.2f}"
    memory_value = "--" if stats.memory_percent is None else f"{round(stats.memory_percent)}%"
    disk_value = "--" if stats.disk_percent is None else f"{round(stats.disk_percent)}%"
    draw_metric(
        draw,
        5,
        62,
        "LOAD",
        load_value,
        load_ratio(stats),
        "load" in issues,
        black,
        accent,
        label_font,
        metric_font,
    )
    draw_metric(
        draw,
        75,
        62,
        "MEM",
        memory_value,
        None if stats.memory_percent is None else stats.memory_percent / 100,
        "memory" in issues,
        black,
        accent,
        label_font,
        metric_font,
    )
    draw_metric(
        draw,
        145,
        62,
        "DISK",
        disk_value,
        None if stats.disk_percent is None else stats.disk_percent / 100,
        "disk" in issues,
        black,
        accent,
        label_font,
        metric_font,
    )

    draw.line((5, 87, WIDTH - 5, 87), fill=black)
    wifi_value = "--" if stats.wifi_dbm is None else f"{round(stats.wifi_dbm)} DBM"
    wifi_colour = accent if "wifi" in issues else black
    draw.text((5, 91), f"WIFI {wifi_value}", fill=wifi_colour, font=footer_font)
    right_aligned(draw, WIDTH - 5, 91, stats.ip_address, black, footer_font)

    return image, display


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preview",
        type=Path,
        help="write a PNG preview instead of refreshing the physical display",
    )
    args = parser.parse_args()

    try:
        image, display = render(collect_health(), preview=args.preview is not None)
        if args.preview:
            image.save(args.preview)
            print(f"Preview written to {args.preview}")
        else:
            display.set_image(image)
            display.show()
            print("Pi health dashboard refreshed successfully")
        return 0
    except Exception as exc:
        print(f"Pi health dashboard update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
