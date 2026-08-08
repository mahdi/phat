#!/usr/bin/env python3
"""Display the Lion and Sun emblem centred in red."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

WIDTH = 212
HEIGHT = 104
ASSET_PATH = Path(__file__).resolve().parents[1] / "assets" / "lion-and-sun-mono.png"


def emblem_mask(asset_path=ASSET_PATH):
    source = Image.open(asset_path).convert("L")
    mask = ImageOps.invert(source)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError(f"Emblem asset contains no visible artwork: {asset_path}")

    mask = mask.crop(bounds)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    mask.thumbnail((WIDTH - 6, HEIGHT - 4), resampling)
    return mask.point(lambda value: 255 if value >= 96 else 0)


def render(preview=False):
    if preview:
        white, accent = (255, 255, 255), (190, 0, 0)
        image = Image.new("RGB", (WIDTH, HEIGHT), white)
        display = None
    else:
        from inky import InkyPHAT

        display = InkyPHAT("red")
        display.set_border(display.WHITE)
        white, accent = display.WHITE, display.RED
        image = Image.new("P", (display.WIDTH, display.HEIGHT), white)

    mask = emblem_mask()
    position = ((WIDTH - mask.width) // 2, (HEIGHT - mask.height) // 2)
    image.paste(accent, position, mask)
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
        image, display = render(preview=args.preview is not None)
        if args.preview:
            image.save(args.preview)
            print(f"Preview written to {args.preview}")
        else:
            display.set_image(image)
            display.show()
            print("Lion and Sun emblem refreshed successfully")
        return 0
    except Exception as exc:
        print(f"Emblem display update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
