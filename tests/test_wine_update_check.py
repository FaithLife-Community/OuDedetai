import unittest
from unittest import mock

from ou_dedetai import utils
from ou_dedetai.wine import WineRelease


INSTALLED = "/x/data/bin/wine-distribution/wine-custom_11.21_oinos-pre-aaa-x86_64/bin/wine"


class TestSameVersionUpdate(unittest.TestCase):
    def app(self, appimage=None, wine_binary=INSTALLED):
        app = mock.Mock()
        app.conf.wine_appimage_path = appimage
        app.conf.is_wine_binary_in_distribution = appimage is None
        app.conf.wine_binary = wine_binary
        app.conf.wine_recommended_version = "11.21"
        app.conf._wine_tarball_release.download_url = "https://e/wine-custom_11.21_oinos-pre-bbb-x86_64.tar.xz"
        app.conf.wine_download_url = "https://e/wine-custom_11.21_oinos-pre-bbb-x86_64.AppImage"
        return app

    def compare(self, app):
        with mock.patch.object(utils.wine, "get_wine_release", return_value=(WineRelease(11, 21, "oinos"), "")):
            return utils.compare_recommended_wine_version(app)[0]

    def test_a_newer_build_of_the_same_version_is_an_update(self):
        self.assertEqual(self.compare(self.app()), 0)
        self.assertEqual(self.compare(self.app(appimage="/x/wine-custom_11.21_oinos-pre-aaa-x86_64.AppImage")), 0)

    def test_the_same_build_is_up_to_date(self):
        app = self.app(wine_binary="/x/data/bin/wine-distribution/wine-custom_11.21_oinos-pre-bbb-x86_64/bin/wine")
        self.assertEqual(self.compare(app), 1)
        app = self.app(appimage="/x/data/bin/wine-custom_11.21_oinos-pre-bbb-x86_64.AppImage")
        self.assertEqual(self.compare(app), 1)

    def test_a_wine_not_managed_by_oudedetai_keeps_the_version_check(self):
        app = self.app(wine_binary="/usr/bin/wine")
        app.conf.is_wine_binary_in_distribution = False
        self.assertEqual(self.compare(app), 1)

    def test_build_names_ignore_the_package_format(self):
        self.assertEqual(utils.wine_build_name("w-x86_64.AppImage"), utils.wine_build_name("w-x86_64.tar.xz"))


if __name__ == "__main__":
    unittest.main()
