import unittest
from datetime import datetime

from inky_dashboard.widgets.weather import next_rain_hours, uv_label


class WeatherTests(unittest.TestCase):
    def test_uv_labels(self):
        self.assertEqual(uv_label(0), "LOW")
        self.assertEqual(uv_label(3), "MOD")
        self.assertEqual(uv_label(6), "HIGH")
        self.assertEqual(uv_label(8), "V HIGH")
        self.assertEqual(uv_label(11), "EXTREME")

    def test_rain_outlook_returns_only_future_hours(self):
        payload = {
            "hourly": {
                "time": [
                    "2026-08-08T11:00",
                    "2026-08-08T12:00",
                    "2026-08-08T13:00",
                    "2026-08-08T14:00",
                ],
                "precipitation_probability": [10, 20, 30, None],
            }
        }
        result = next_rain_hours(payload, datetime.fromisoformat("2026-08-08T11:30"))
        self.assertEqual([probability for _, probability in result], [20, 30, 0])


if __name__ == "__main__":
    unittest.main()
