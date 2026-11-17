import unittest

from ou_dedetai import wine


class TestFontReplacements(unittest.TestCase):
    def test_replacements_point_at_open_fonts(self):
        self.assertEqual(wine.FONT_REPLACEMENTS["Georgia"][0], "Gelasio")
        self.assertEqual(wine.FONT_REPLACEMENTS["Source Sans Pro"], ["Source Sans 3"])
        self.assertEqual(wine.FONT_REPLACEMENTS["Arial"][0], "Liberation Sans")


if __name__ == "__main__":
    unittest.main()
