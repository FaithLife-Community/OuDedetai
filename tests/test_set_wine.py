import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import utils


class TestSetWine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bindir = self.tmp / "data/bin"
        self.bindir.mkdir(parents=True)
        self.app = mock.Mock()
        self.app.conf.installer_binary_dir = str(self.bindir)
        self.app.conf.wine_appimage_link_file_name = "selected_wine.AppImage"
        self.app.conf.wine_download_file_name = "wine-recommended.AppImage"

    def test_an_appimage_replaces_a_tarball_wine(self):
        # an install running an unpacked tarball
        for name in ("wine", "wine64", "wineserver"):
            (self.bindir / name).symlink_to("/old/distribution/bin/wine")
        self.app.conf.wine_binary = "/old/distribution/bin/wine"
        appimage = self.tmp / "wine-custom_11.22_oinos-pre-x-x86_64.AppImage"
        appimage.write_text("")
        self.app.conf.wine_appimage_path = str(appimage)
        with mock.patch.object(utils, "check_appimage", return_value=True):
            utils.set_appimage_symlink(self.app)
        copied = self.bindir / appimage.name
        self.assertTrue(copied.is_file())
        self.assertEqual(self.app.conf.wine_binary, str(copied))
        self.assertEqual(os.readlink(self.bindir / "selected_wine.AppImage"), str(copied))
        for name in ("wine", "wine64", "wineserver", "winetricks"):
            self.assertEqual(os.readlink(self.bindir / name), "./selected_wine.AppImage")

    def test_a_tarball_is_unpacked_through_setup_wine(self):
        tarball = self.tmp / "wine-custom_11.22_oinos-pre-x-x86_64.tar.xz"
        tarball.write_bytes(b"")
        self.app.conf.wine_appimage_path = str(tarball)
        with mock.patch.object(utils.wine, "is_wine_tarball", return_value=True), \
                mock.patch.object(utils.wine, "setup_wine") as setup:
            utils.set_appimage_symlink(self.app)
        self.assertIsNone(self.app.conf.wine_appimage_path)
        self.assertEqual(self.app.conf.wine_binary, str(tarball))
        setup.assert_called_once_with(self.app)


if __name__ == "__main__":
    unittest.main()
