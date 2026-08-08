import json
import sys
import tempfile
import unittest
from pathlib import Path

from inky_dashboard.rotation import (
    expanded_command,
    load_widgets,
    select_next,
)


class RotationTests(unittest.TestCase):
    def write_config(self, widgets):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "widgets.json"
        path.write_text(json.dumps({"widgets": widgets}), encoding="utf-8")
        return path

    def test_disabled_widgets_are_excluded(self):
        path = self.write_config(
            [
                {"id": "weather", "command": ["weather"]},
                {"id": "off", "enabled": False, "command": ["off"]},
            ]
        )
        self.assertEqual([widget["id"] for widget in load_widgets(path)], ["weather"])

    def test_select_next_wraps_in_config_order(self):
        widgets = [{"id": "weather"}, {"id": "bitcoin"}]
        self.assertEqual(select_next(widgets, None)["id"], "weather")
        self.assertEqual(select_next(widgets, "weather")["id"], "bitcoin")
        self.assertEqual(select_next(widgets, "bitcoin")["id"], "weather")

    def test_duplicate_ids_are_rejected(self):
        path = self.write_config(
            [
                {"id": "same", "command": ["one"]},
                {"id": "same", "command": ["two"]},
            ]
        )
        with self.assertRaisesRegex(ValueError, "Duplicate widget id"):
            load_widgets(path)

    def test_python_placeholder_uses_active_interpreter(self):
        command = expanded_command({"command": ["{python}", "-m", "demo"]})
        self.assertEqual(command, [sys.executable, "-m", "demo"])


if __name__ == "__main__":
    unittest.main()
