#!/usr/bin/env python3
"""Render the current BTC/USD spot price on a red 212x104 Inky pHAT."""

import argparse
import json
import sys
import urllib.request
from datetime import datetime
from decimal import Decimal, DecimalException
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inky_dashboard.paths import font_path

STATS_URL = "https://api.exchange.coinbase.com/products/BTC-USD/stats"
WIDTH = 212
HEIGHT = 104


def parse_market(payload):
    try:
        price = Decimal(payload["last"])
        opening_price = Decimal(payload["open"])
        if opening_price == 0:
            raise ValueError("Opening price cannot be zero")
        change_24h = ((price - opening_price) / opening_price) * Decimal("100")
        return price, change_24h
    except (KeyError, DecimalException, TypeError, ValueError) as exc:
        raise RuntimeError("Coinbase returned unexpected market stats") from exc


def fetch_market():
    request = urllib.request.Request(
        STATS_URL,
        headers={"User-Agent": "pi-inky-bitcoin-display/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return parse_market(json.load(response))


def trend_for_change(change_24h):
    return ("▼", True) if change_24h < 0 else ("▲", False)


def render(price: Decimal, change_24h: Decimal, preview: bool):
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
    title_font = ImageFont.truetype(str(font_path()), 18)
    price_font = ImageFont.truetype(str(font_path()), 32)
    detail_font = ImageFont.truetype(str(font_path(bold=False)), 8)
    change_font = ImageFont.truetype(str(font_path()), 10)

    updated = datetime.now().astimezone().strftime("UPDATED %d %b %Y %H:%M %Z").upper()
    direction, is_down = trend_for_change(change_24h)
    price_colour = accent if is_down else black
    price_text = f"${price:,.0f}"
    change_text = f"24H {direction} {abs(change_24h):.2f}%"

    draw.text(
        (9, 7),
        "BTC / USD",
        fill=black,
        font=title_font,
        stroke_width=1,
        stroke_fill=black,
    )
    draw.line((9, 29, 203, 29), fill=accent, width=2)
    draw.text((9, 34), price_text, fill=price_colour, font=price_font)
    price_box = draw.textbbox((0, 0), price_text, font=price_font)
    price_width = price_box[2] - price_box[0]
    digit_box = draw.textbbox((0, 0), "0123456789", font=price_font)
    arrow_box = draw.textbbox((0, 0), direction, font=price_font)
    # Give the triangle a one-pixel optical lift to match the digit baseline.
    arrow_y = 33 + digit_box[3] - arrow_box[3]
    draw.text(
        (9 + price_width + 7, arrow_y),
        direction,
        fill=price_colour,
        font=price_font,
    )
    draw.text((9, 77), updated, fill=black, font=detail_font)
    draw.text((9, 89), change_text, fill=price_colour, font=change_font)

    return image, display


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview",
        type=Path,
        help="write a PNG preview instead of refreshing the physical display",
    )
    args = parser.parse_args()

    try:
        price, change_24h = fetch_market()
        image, display = render(price, change_24h, preview=args.preview is not None)

        if args.preview:
            image.save(args.preview)
            print(f"Preview written to {args.preview}")
        else:
            display.set_image(image)
            display.show()
            print("Inky pHAT refreshed successfully")
        return 0
    except Exception as exc:
        print(f"Bitcoin display update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
