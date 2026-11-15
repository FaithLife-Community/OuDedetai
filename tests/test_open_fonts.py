import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import wine


class TestInstallOpenFonts(unittest.TestCase):
    def test_downloads_missing_fonts_and_registers_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = mock.Mock()
            app.conf.wine_prefix = f"{tmp}/prefix"
            app.conf.download_dir = f"{tmp}/downloads"
            Path(app.conf.download_dir).mkdir()
            fonts_dir = Path(app.conf.wine_prefix) / "drive_c" / "windows" / "Fonts"
            fonts_dir.mkdir(parents=True)
            (fonts_dir / "Gelasio-Regular.ttf").write_text("already here")

            def fake_download(url, file, targetdir, app):
                (Path(targetdir) / file).write_text(url)

            with mock.patch.object(wine.network, "logos_reuse_download", side_effect=fake_download) as dl, \
                    mock.patch.object(wine, "wine_reg_install") as reg:
                wine.install_open_fonts(app)

            self.assertEqual(dl.call_count, len(wine.OPEN_FONTS) - 1)
            self.assertEqual((fonts_dir / "Gelasio-Regular.ttf").read_text(), "already here")
            self.assertTrue((fonts_dir / "SourceSans3-BoldIt.ttf").exists())
            reg_text = reg.call_args.args[2]
            for name, url in wine.OPEN_FONTS.items():
                self.assertIn(f'"{name}"="{url.rsplit("/", 1)[1]}"', reg_text)

    def test_replacements_point_at_open_fonts(self):
        self.assertEqual(wine.FONT_REPLACEMENTS["Georgia"][0], "Gelasio")
        self.assertEqual(wine.FONT_REPLACEMENTS["Source Sans Pro"], ["Source Sans 3"])
        self.assertEqual(wine.FONT_REPLACEMENTS["Arial"][0], "Liberation Sans")


if __name__ == "__main__":
    unittest.main()
