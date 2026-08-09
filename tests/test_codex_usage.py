import unittest
from datetime import datetime, timedelta, timezone

from inky_dashboard.codex_sync import build_snapshot, split_destination, window_label
from inky_dashboard.widgets.codex_usage import (
    HEIGHT,
    WIDTH,
    UsageSnapshot,
    UsageWindow,
    is_stale,
    logo_masks,
    parse_snapshot,
    render,
    reset_text,
)


def app_server_result():
    return {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 10,
                "windowDurationMins": 10080,
                "resetsAt": 1786874530,
            },
            "secondary": None,
            "planType": "plus",
            "credits": {"balance": "0"},
        },
        "sensitiveUnexpectedField": "must not be copied",
    }


class CodexUsageTests(unittest.TestCase):
    def test_build_snapshot_sanitizes_the_app_server_result(self):
        now = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
        snapshot = build_snapshot(app_server_result(), now=now)
        self.assertEqual(snapshot["plan_type"], "plus")
        self.assertEqual(snapshot["limits"][0]["label"], "WEEKLY")
        self.assertEqual(snapshot["limits"][0]["remaining_percent"], 90)
        self.assertNotIn("sensitiveUnexpectedField", snapshot)
        self.assertNotIn("credits", snapshot)

    def test_window_labels_cover_common_quota_periods(self):
        self.assertEqual(window_label(300), "5-HOUR")
        self.assertEqual(window_label(10080), "WEEKLY")
        self.assertEqual(window_label(2880), "2-DAY")

    def test_destination_rejects_shell_metacharacters(self):
        self.assertEqual(
            split_destination("pi@raspberrypi.local:/home/pi/usage.json"),
            ("pi@raspberrypi.local", "/home/pi/usage.json"),
        )
        with self.assertRaises(ValueError):
            split_destination("pi@host:/tmp/usage.json;touch_bad")

    def test_parse_snapshot_and_stale_age(self):
        payload = build_snapshot(app_server_result())
        snapshot = parse_snapshot(payload)
        self.assertEqual(snapshot.plan_type, "plus")
        self.assertEqual(snapshot.limits[0].remaining_percent, 90)
        self.assertFalse(is_stale(snapshot, now=snapshot.updated_at + timedelta(hours=5)))
        self.assertTrue(is_stale(snapshot, now=snapshot.updated_at + timedelta(hours=7)))

    def test_preview_uses_the_display_dimensions_and_palette(self):
        now = datetime.now(timezone.utc)
        snapshot = UsageSnapshot(
            plan_type="plus",
            updated_at=now,
            limits=(UsageWindow("WEEKLY", 10, 90, now + timedelta(days=7)),),
        )
        image, display = render(snapshot, preview=True)
        self.assertIsNone(display)
        self.assertEqual(image.size, (WIDTH, HEIGHT))
        colours = {colour for _, colour in image.getcolors(maxcolors=WIDTH * HEIGHT)}
        self.assertIn((190, 0, 0), colours)
        self.assertIn((0, 0, 0), colours)
        self.assertIn((255, 255, 255), colours)

    def test_logo_and_reset_details_are_display_ready(self):
        silhouette, glyph = logo_masks()
        self.assertLessEqual(silhouette.width, 17)
        self.assertLessEqual(silhouette.height, 17)
        self.assertIsNotNone(silhouette.getbbox())
        self.assertIsNotNone(glyph.getbbox())

        reset_at = datetime(2026, 8, 16, 10, 2, tzinfo=timezone.utc)
        window = UsageWindow("WEEKLY", 17, 83, reset_at)
        self.assertTrue(reset_text(window).startswith("SUN 16 AUG"))


if __name__ == "__main__":
    unittest.main()
