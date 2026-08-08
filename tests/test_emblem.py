import unittest

from inky_dashboard.widgets.emblem import HEIGHT, WIDTH, emblem_mask, render


class EmblemTests(unittest.TestCase):
    def test_mask_fits_display(self):
        mask = emblem_mask()
        self.assertLessEqual(mask.width, WIDTH)
        self.assertLessEqual(mask.height, HEIGHT)
        self.assertGreater(mask.getbbox()[2], 0)

    def test_preview_is_centred_red_on_white(self):
        image, display = render(preview=True)
        self.assertIsNone(display)
        self.assertEqual(image.size, (WIDTH, HEIGHT))
        colours = {colour for _, colour in image.getcolors(maxcolors=WIDTH * HEIGHT)}
        self.assertIn((190, 0, 0), colours)


if __name__ == "__main__":
    unittest.main()
