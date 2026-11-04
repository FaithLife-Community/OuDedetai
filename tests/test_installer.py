import io
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ou_dedetai import installer, wine
from ou_dedetai.config import Config, LegacyConfiguration, PersistentConfiguration
from . import TESTDATADIR


class TestLocalRunner(unittest.TestCase):
    def test_switch_between_local_appimage_and_tarballs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = Mock()
            conf = object.__new__(Config)
            conf.app = app
            conf._raw = PersistentConfiguration(install_dir=tmp, faithlife_product='Logos')
            conf._overrides = SimpleNamespace(install_dir=None, installer_binary_dir=None,
                                             wine_appimage_path=None, wine_appimage_link_file_name=None)
            app.conf = conf
            source = root / 'custom.AppImage'
            shutil.copy(TESTDATADIR / 'wine_tiny_v2.AppImage', source)
            source.chmod(0o640)
            bindir = Path(conf.installer_binary_dir)
            with patch.object(LegacyConfiguration, 'config_file_path', return_value=str(root / 'config.json')), \
                    patch.object(installer.network, 'logos_reuse_download') as download:
                # Exercise two different distributions so stale directories cannot select the old runner.
                for runner in (source, 'wine-one', 'wine-two', source):
                    if isinstance(runner, str):
                        archive = root / f'{runner}.tar.gz'
                        with tarfile.open(archive, 'w:gz') as tar:
                            for binary in ('wine', 'wineserver', 'winetricks'):
                                member = tarfile.TarInfo(f'{runner}/bin/{binary}')
                                member.mode = 0o755
                                member.size = len(b'#!/bin/sh')
                                tar.addfile(member, io.BytesIO(b'#!/bin/sh'))
                        selection = archive
                    else:
                        selection = runner
                    conf.wine_binary = str(selection)
                    wine.setup_wine(app)
                    self.assertEqual((bindir / 'wine').resolve(), Path(conf.wine_binary).resolve())
                    self.assertEqual((bindir / 'wine64').resolve(), Path(conf.wine_binary).resolve())
                    if selection == source:
                        self.assertEqual(Path(conf.wine_binary).stat().st_mode & 0o777, 0o740)
                        self.assertEqual(Path(conf.wine_binary).read_bytes(), source.read_bytes())
                    else:
                        self.assertEqual(Path(conf.wine_binary).parent.parent.name, runner)
                        self.assertEqual(conf.wine_path_in_distribution, conf.wine_binary)
                        self.assertIsNone(conf.wine_appimage_path)
                download.assert_not_called()
