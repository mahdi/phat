import unittest

from inky_dashboard.widgets.health import (
    HEIGHT,
    WIDTH,
    HealthStats,
    format_uptime,
    health_issues,
    parse_meminfo,
    parse_wifi_dbm,
    render,
)


def sample_stats(**changes):
    values = {
        "hostname": "RASPBERRYPI",
        "temperature_c": 48.2,
        "uptime_seconds": 35342,
        "load_one": 0.29,
        "cpu_count": 1,
        "memory_percent": 44.1,
        "disk_percent": 13.0,
        "wifi_dbm": -55.0,
        "ip_address": "192.168.1.101",
    }
    values.update(changes)
    return HealthStats(**values)


class HealthTests(unittest.TestCase):
    def test_parse_meminfo_uses_available_memory(self):
        text = "MemTotal: 1000 kB\nMemAvailable: 440 kB\n"
        self.assertAlmostEqual(parse_meminfo(text), 56.0)

    def test_parse_wifi_signal(self):
        text = "wlan0: 0000   55.  -55.  -256  0  0  0  0  0  0"
        self.assertEqual(parse_wifi_dbm(text), -55.0)

    def test_format_uptime(self):
        self.assertEqual(format_uptime(35342), "9H 49M")
        self.assertEqual(format_uptime(190800), "2D 5H")

    def test_health_issues_apply_thresholds(self):
        self.assertEqual(health_issues(sample_stats()), [])
        self.assertEqual(
            health_issues(sample_stats(temperature_c=80, disk_percent=92)),
            ["temperature", "disk"],
        )

    def test_preview_uses_the_display_dimensions_and_palette(self):
        image, display = render(sample_stats(), preview=True)
        self.assertIsNone(display)
        self.assertEqual(image.size, (WIDTH, HEIGHT))
        colours = {colour for _, colour in image.getcolors(maxcolors=WIDTH * HEIGHT)}
        self.assertIn((190, 0, 0), colours)
        self.assertIn((0, 0, 0), colours)
        self.assertIn((255, 255, 255), colours)


if __name__ == "__main__":
    unittest.main()
