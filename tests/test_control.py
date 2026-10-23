import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ou_dedetai.constants as constants
import ou_dedetai.control as control


class TestUninstall(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.home = Path(self.tempdir.name) / 'home'
        self.home.mkdir()
        self.config_file = self.home / '.config' / 'FaithLife-Community' / 'oudedetai.json'
        self.config_file.parent.mkdir(parents=True)
        self.config_file.write_text('{}')

        self.app = Mock()
        self.app.approve.return_value = True  # yes to uninstall, yes to clear cache/logs
        self.app.conf.config_file_path = str(self.config_file)
        self.cache_dir = self.home / '.cache' / 'FaithLife-Community'
        self.state_dir = self.home / '.local' / 'state' / 'FaithLife-Community'
        for d in (self.cache_dir, self.state_dir):
            d.mkdir(parents=True)

        patches = [
            patch.dict(os.environ, {'HOME': str(self.home)}),
            patch.object(constants, 'CACHE_DIR', str(self.cache_dir)),
            # STATE_DIR keeps a literal "~" when XDG_STATE_HOME is unset
            patch.object(constants, 'STATE_DIR', '~/.local/state/FaithLife-Community'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def make_install(self, install_dir: Path) -> Path:
        (install_dir / 'data' / 'wine64_bottle').mkdir(parents=True)
        self.app.conf._raw.install_dir = str(install_dir)
        return install_dir

    def test_removes_install_config_cache_and_logs(self):
        install_dir = self.make_install(self.home / '.local' / 'share' / 'FaithLife-Community' / 'oudedetai')
        control.uninstall(self.app)
        for path in (install_dir, self.config_file, self.cache_dir, self.state_dir):
            self.assertFalse(path.exists(), path)

    def test_removes_symlinked_install(self):
        # e.g. the install was moved to another drive and linked back
        real_install = self.make_install(Path(self.tempdir.name) / 'other-drive' / 'oudedetai')
        link = self.home / 'LogosBible10'
        link.symlink_to(real_install)
        self.app.conf._raw.install_dir = str(link)
        control.uninstall(self.app)
        self.assertFalse(link.is_symlink())
        self.assertFalse(real_install.exists())

    def test_final_status_names_what_was_kept(self):
        not_install = self.home / 'Documents'
        not_install.mkdir()
        self.app.conf._raw.install_dir = str(not_install)
        control.uninstall(self.app)
        final_status = self.app.status.call_args_list[-1].args[0]
        self.assertIn(str(not_install), final_status)

    def test_never_removes_home(self):
        self.make_install(self.home)  # install_dir set to ~
        keep = self.home / 'Documents' / 'sermon.txt'
        keep.parent.mkdir()
        keep.write_text('keep me')
        control.uninstall(self.app)
        self.assertTrue(keep.exists())

    def test_keeps_install_dir_that_is_not_an_install(self):
        not_install = self.home / 'Documents'
        not_install.mkdir()
        (not_install / 'sermon.txt').write_text('keep me')
        self.app.conf._raw.install_dir = str(not_install)
        control.uninstall(self.app)
        self.assertTrue((not_install / 'sermon.txt').exists())

    def test_keeps_downloads_with_the_downloaded_binary(self):
        downloads = self.home / 'Downloads'
        downloads.mkdir()
        (downloads / constants.BINARY_NAME).write_text('the downloaded app')
        (downloads / 'photo.jpg').write_text('keep me')
        self.app.conf._raw.install_dir = str(downloads)
        control.uninstall(self.app)
        self.assertTrue((downloads / 'photo.jpg').exists())

    def test_keeps_cache_root_when_cache_dir_is_not_ours(self):
        # With XDG_CACHE_HOME set, CACHE_DIR is the whole cache root
        cache_root = self.home / '.cache'
        other_app = cache_root / 'other-app' / 'data'
        other_app.mkdir(parents=True)
        self.make_install(self.home / 'LogosBible10')
        with patch.object(constants, 'CACHE_DIR', str(cache_root)):
            control.uninstall(self.app)
        self.assertTrue(other_app.exists())


if __name__ == '__main__':
    unittest.main()
