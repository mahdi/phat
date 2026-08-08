import unittest
from datetime import datetime, timedelta, timezone

from inky_dashboard.widgets.speedtest import (
    HEIGHT,
    WIDTH,
    SpeedResult,
    cache_is_fresh,
    format_speed,
    parse_result,
    render,
)


def sample_payload():
    return {
        "type": "result",
        "timestamp": "2026-08-08T18:42:00Z",
        "ping": {"jitter": 0.7, "latency": 5.2},
        "download": {"bandwidth": 9_175_000, "bytes": 45_000_000},
        "upload": {"bandwidth": 3_975_000, "bytes": 20_000_000},
        "isp": "Hyperoptic Ltd",
    }


class SpeedtestTests(unittest.TestCase):
    def test_parse_result_converts_bytes_per_second_to_mbps(self):
        result = parse_result(sample_payload())
        self.assertEqual(result.provider, "Hyperoptic Ltd")
        self.assertAlmostEqual(result.download_mbps, 73.4)
        self.assertAlmostEqual(result.upload_mbps, 31.8)
        self.assertAlmostEqual(result.ping_ms, 5.2)
        self.assertEqual(result.tested_at, datetime(2026, 8, 8, 18, 42, tzinfo=timezone.utc))

    def test_parse_result_rejects_invalid_data(self):
        payload = sample_payload()
        payload["download"]["bandwidth"] = -1
        with self.assertRaises(RuntimeError):
            parse_result(payload)

    def test_cache_freshness_uses_test_timestamp(self):
        result = parse_result(sample_payload())
        self.assertTrue(
            cache_is_fresh(
                result,
                60,
                now=result.tested_at + timedelta(minutes=59),
            )
        )
        self.assertFalse(
            cache_is_fresh(
                result,
                60,
                now=result.tested_at + timedelta(minutes=61),
            )
        )

    def test_speed_format_keeps_large_values_compact(self):
        self.assertEqual(format_speed(73.45), "73.5")
        self.assertEqual(format_speed(942.13), "942")

    def test_preview_uses_the_display_dimensions_and_palette(self):
        result = SpeedResult(
            provider="Hyperoptic Ltd",
            download_mbps=73.4,
            upload_mbps=31.8,
            ping_ms=5.2,
            tested_at=datetime.now(timezone.utc),
        )
        image, display = render(result, preview=True)
        self.assertIsNone(display)
        self.assertEqual(image.size, (WIDTH, HEIGHT))
        colours = {colour for _, colour in image.getcolors(maxcolors=WIDTH * HEIGHT)}
        self.assertIn((190, 0, 0), colours)
        self.assertIn((0, 0, 0), colours)
        self.assertIn((255, 255, 255), colours)


if __name__ == "__main__":
    unittest.main()
