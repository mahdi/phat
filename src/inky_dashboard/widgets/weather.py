#!/usr/bin/env python3
"""Render a compact London weather dashboard on a red 212x104 Inky pHAT."""

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inky_dashboard.paths import font_path, state_dir

CACHE_PATH = state_dir() / "weather-cache.json"
AIR_CACHE_PATH = state_dir() / "air-quality-cache.json"
WIDTH = 212
HEIGHT = 104
LOCATION = "LONDON"
LATITUDE = 51.5074
LONGITUDE = -0.1278
TIMEZONE = "Europe/London"


def font(name: str, size: int):
    return ImageFont.truetype(str(font_path(bold="Medium" not in name)), size)


def fetch_weather():
    params = urllib.parse.urlencode(
        {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "current": (
                "temperature_2m,apparent_temperature,weather_code,is_day,relative_humidity_2m"
            ),
            "hourly": "precipitation_probability",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": TIMEZONE,
            "forecast_days": 2,
        }
    )
    request = urllib.request.Request(
        f"https://api.open-meteo.com/v1/forecast?{params}",
        headers={"User-Agent": "pi-inky-london-weather/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        return payload, False
    except Exception:
        if not CACHE_PATH.exists():
            raise
        return json.loads(CACHE_PATH.read_text(encoding="utf-8")), True


def fetch_air_quality():
    params = urllib.parse.urlencode(
        {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "current": "european_aqi,uv_index",
            "timezone": TIMEZONE,
        }
    )
    request = urllib.request.Request(
        f"https://air-quality-api.open-meteo.com/v1/air-quality?{params}",
        headers={"User-Agent": "pi-inky-london-weather/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        AIR_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        return payload, False
    except Exception:
        if AIR_CACHE_PATH.exists():
            return json.loads(AIR_CACHE_PATH.read_text(encoding="utf-8")), True
        return {"current": {"european_aqi": None, "uv_index": None}}, True


def next_rain_hours(payload, current_time, count=3):
    hours = [datetime.fromisoformat(value) for value in payload["hourly"]["time"]]
    probabilities = payload["hourly"]["precipitation_probability"]
    upcoming = [
        (hour, int(probability or 0))
        for hour, probability in zip(hours, probabilities)
        if hour > current_time
    ]
    return upcoming[:count]


def draw_sun(draw, cx, cy, radius, accent):
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=accent)
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        x1 = cx + math.cos(radians) * (radius + 3)
        y1 = cy + math.sin(radians) * (radius + 3)
        x2 = cx + math.cos(radians) * (radius + 7)
        y2 = cy + math.sin(radians) * (radius + 7)
        draw.line((x1, y1, x2, y2), fill=accent, width=2)


def draw_moon(draw, cx, cy, radius, black, white):
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=black)
    draw.ellipse(
        (cx - radius + 6, cy - radius - 2, cx + radius + 5, cy + radius - 2),
        fill=white,
    )


def draw_cloud(draw, x, y, black):
    draw.ellipse((x + 4, y + 11, x + 25, y + 29), fill=black)
    draw.ellipse((x + 14, y + 4, x + 36, y + 28), fill=black)
    draw.ellipse((x + 27, y + 12, x + 43, y + 29), fill=black)
    draw.rectangle((x + 7, y + 19, x + 39, y + 29), fill=black)


def draw_weather_icon(draw, code, is_day, x, y, black, white, accent):
    if code == 0:
        if is_day:
            draw_sun(draw, x + 22, y + 20, 8, accent)
        else:
            draw_moon(draw, x + 22, y + 20, 11, black, white)
        return

    if code in (1, 2):
        if is_day:
            draw_sun(draw, x + 13, y + 11, 6, accent)
        else:
            draw_moon(draw, x + 13, y + 11, 8, accent, white)
        draw_cloud(draw, x + 3, y + 8, black)
        return

    if code == 3:
        draw_cloud(draw, x + 1, y + 5, black)
        return

    if code in (45, 48):
        draw_cloud(draw, x + 1, y, black)
        for offset in (30, 35, 40):
            draw.line((x + 5, y + offset, x + 42, y + offset), fill=accent, width=2)
        return

    draw_cloud(draw, x + 1, y, black)

    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        for offset in (10, 22, 34):
            draw.line((x + offset, y + 32, x + offset - 3, y + 39), fill=accent, width=2)
    elif code in (71, 73, 75, 77, 85, 86):
        for offset in (11, 24, 37):
            cx, cy = x + offset, y + 36
            draw.line((cx - 3, cy, cx + 3, cy), fill=accent, width=1)
            draw.line((cx, cy - 3, cx, cy + 3), fill=accent, width=1)
            draw.line((cx - 2, cy - 2, cx + 2, cy + 2), fill=accent, width=1)
            draw.line((cx - 2, cy + 2, cx + 2, cy - 2), fill=accent, width=1)
    elif code in (95, 96, 99):
        draw.polygon(
            (
                (x + 25, y + 29),
                (x + 17, y + 39),
                (x + 24, y + 38),
                (x + 19, y + 47),
                (x + 34, y + 34),
                (x + 27, y + 35),
            ),
            fill=accent,
        )


def draw_drop(draw, x, y, accent):
    draw.polygon(((x + 5, y), (x, y + 9), (x + 10, y + 9)), fill=accent)
    draw.ellipse((x, y + 4, x + 10, y + 13), fill=accent)


def uv_label(value):
    if value is None:
        return "OFFLINE"
    if value < 3:
        return "LOW"
    if value < 6:
        return "MOD"
    if value < 8:
        return "HIGH"
    if value < 11:
        return "V HIGH"
    return "EXTREME"


def right_aligned(draw, xy, text, fill, text_font):
    x, y = xy
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text((x - (box[2] - box[0]), y), text, fill=fill, font=text_font)


def render(payload, air_payload, stale=False, preview=False):
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
    header_font = font("JetBrainsMonoNL-ExtraBold.ttf", 12)
    location_font = font("JetBrainsMonoNL-ExtraBold.ttf", 12)
    temperature_font = font("JetBrainsMonoNL-ExtraBold.ttf", 28)
    label_font = font("JetBrainsMonoNL-Bold.ttf", 9)
    detail_font = font("JetBrainsMonoNL-Medium.ttf", 8)
    card_value_font = font("JetBrainsMonoNL-ExtraBold.ttf", 13)
    tiny_font = font("JetBrainsMonoNL-Bold.ttf", 7)
    bottom_font = font("JetBrainsMonoNL-ExtraBold.ttf", 10)

    current = payload["current"]
    now = datetime.fromisoformat(current["time"])
    temperature = round(current["temperature_2m"])
    feels_like = round(current["apparent_temperature"])
    high = round(payload["daily"]["temperature_2m_max"][0])
    low = round(payload["daily"]["temperature_2m_min"][0])
    rain_hours = next_rain_hours(payload, now)
    rain_max = max((probability for _, probability in rain_hours), default=0)
    aqi_raw = air_payload.get("current", {}).get("european_aqi")
    aqi = round(aqi_raw) if aqi_raw is not None else None
    humidity_raw = current.get("relative_humidity_2m")
    humidity = round(humidity_raw) if humidity_raw is not None else None
    uv_raw = air_payload.get("current", {}).get("uv_index")
    uv_index = round(uv_raw, 1) if uv_raw is not None else None

    # Red masthead.
    draw.rectangle((0, 0, WIDTH - 1, 19), fill=accent)
    draw.text((5, 2), now.strftime("%a %-d %b %Y").upper(), fill=white, font=header_font)
    right_aligned(draw, (WIDTH - 5, 2), LOCATION, white, location_font)

    # Main weather icon and temperature.
    draw_weather_icon(
        draw,
        int(current["weather_code"]),
        bool(current["is_day"]),
        3,
        22,
        black,
        white,
        accent,
    )
    draw.text((54, 22), f"{temperature}°", fill=black, font=temperature_font)
    draw.text((57, 52), f"FEELS {feels_like}°", fill=black, font=detail_font)

    # Rain and air-quality cards beside the temperature.
    draw.rectangle((128, 21, 208, 42), outline=accent)
    draw.rectangle((129, 22, 207, 41), outline=accent)
    draw_drop(draw, 133, 25, accent)
    draw.text((145, 26), "RAIN", fill=black, font=label_font)
    right_aligned(draw, (203, 23), f"{rain_max}%", accent, card_value_font)

    air_colour = accent if aqi is None or aqi > 40 else black
    draw.rectangle((128, 45, 208, 66), outline=accent)
    draw.rectangle((129, 46, 207, 65), outline=accent)
    draw.ellipse((134, 51, 141, 58), fill=air_colour)
    draw.text((145, 49), "AIR Q", fill=black, font=label_font)
    right_aligned(draw, (203, 46), "--" if aqi is None else str(aqi), air_colour, card_value_font)

    # Daily range and update status.
    draw.line((4, 69, 208, 69), fill=black, width=1)
    draw.text((5, 72), f"HIGH {high}°  LOW {low}°", fill=black, font=detail_font)
    update_text = ("STALE " if stale else "") + now.strftime("%H:%M")
    right_aligned(draw, (207, 72), update_text, accent if stale else black, tiny_font)

    # Three-hour rain outlook.
    draw.text((5, 82), "RAIN", fill=accent, font=bottom_font)
    x = 38
    for index, (hour, probability) in enumerate(rain_hours):
        entry = f"{hour:%H} {probability}%"
        draw.text((x, 82), entry, fill=black, font=bottom_font)
        if index < len(rain_hours) - 1:
            x += 50
            draw.line((x - 7, 84, x - 7, 92), fill=accent, width=1)

    # Compact desk-friendly conditions strip.
    uv_text = "--" if uv_index is None else f"{uv_index:g}"
    humidity_text = "--" if humidity is None else f"{humidity}%"
    draw.text((5, 93), f"UV {uv_text} {uv_label(uv_index)}", fill=accent, font=bottom_font)
    right_aligned(draw, (207, 93), f"HUMIDITY {humidity_text}", black, bottom_font)

    return image, display


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview",
        type=Path,
        help="write a PNG preview instead of refreshing the physical display",
    )
    args = parser.parse_args()

    try:
        payload, weather_stale = fetch_weather()
        air_payload, air_stale = fetch_air_quality()
        image, display = render(
            payload,
            air_payload,
            stale=weather_stale or air_stale,
            preview=args.preview is not None,
        )
        if args.preview:
            image.save(args.preview)
            print(f"Preview written to {args.preview}")
        else:
            display.set_image(image)
            display.show()
            print("London weather dashboard refreshed successfully")
        return 0
    except Exception as exc:
        print(f"Weather dashboard update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
