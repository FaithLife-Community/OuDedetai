import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ou_dedetai import constants
from ou_dedetai.config import Config, PersistentConfiguration


class TestRunnerConfig(unittest.TestCase):
    def test_recommended_appimage_url(self):
        conf = object.__new__(Config)
        conf._raw = PersistentConfiguration(wine_binary=constants.WINE_RECOMMENDED_APPIMAGE_SIGIL,
                                            install_dir='/unused', faithlife_product='Logos')
        conf._overrides = SimpleNamespace(install_dir=None)
        conf._network = Mock()
        conf._network.wine_appimage_recommended_url.return_value = 'https://example.org/wine.AppImage'
        self.assertEqual(conf.wine_download_url, 'https://example.org/wine.AppImage')
