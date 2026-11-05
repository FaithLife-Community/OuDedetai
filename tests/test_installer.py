import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ou_dedetai import installer, network


class TestAkousousinInstall(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.app = Mock()
        self.app.installer_step = self.app.installer_step_count = 0
        self.app.conf.download_dir = str(self.root / 'downloads')
        Path(self.app.conf.download_dir).mkdir()
        self.app.conf.wine_prefix = str(self.root / 'prefix with spaces')
        self.app.conf.wine64_binary = '/path with spaces/wine64'
        self.app.exit.side_effect = RuntimeError
        self.target = self.root / 'Akousousin/Akousousin-x86_64.AppImage'
        for name, value in (
            ('constants.XDG_DATA_HOME', str(self.root)),
            ('ensure_product_installed', None),
            ('network._get_release_data', network.SoftwareReleaseInfo('beta-123', 'https://example/image')),
            ('system.run_command', subprocess.CompletedProcess([], 0, '--api-start', '')),
        ):
            target = 'ou_dedetai.installer.' + name
            mock = patch(target, value) if name == 'constants.XDG_DATA_HOME' else patch(target, return_value=value)
            setattr(self, name.split('.')[-1], mock.start())
            self.addCleanup(mock.stop)

    def test_installs_automatically_and_registers_without_starting_service(self):
        def download(url, filename, targetdir, app):
            (Path(targetdir) / filename).write_bytes(b'AppImage fixture')
        with patch.object(installer.network, 'logos_reuse_download', side_effect=download) as reuse:
            installer.ensure_akousousin(self.app)
        self.assertEqual(self.target.read_bytes(), b'AppImage fixture')
        self.assertTrue(self.target.stat().st_mode & 0o100)
        self.assertTrue(reuse.call_args.args[1].startswith('beta-123-'))
        commands = [call.args[0] for call in self.run_command.call_args_list]
        self.assertEqual(commands[-1], [str(self.target), '--wine-prefix', self.app.conf.wine_prefix,
                                        '--wine', self.app.conf.wine64_binary, '--install-only'])
        self.assertEqual(len(commands), 2)
        self.app.ask.assert_not_called()
        self.assertEqual(self.run_command.call_args.kwargs['env']['APPIMAGE_EXTRACT_AND_RUN'], '1')
        self.assertEqual(self.run_command.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')

    def test_existing_shared_install_is_reused_for_this_prefix(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b'existing')
        installer.ensure_akousousin(self.app)
        self._get_release_data.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b'existing')
        self.assertIn('--install-only', self.run_command.call_args.args[0])

    def test_old_engine_is_refused_instead_of_adding_lifecycle_management(self):
        self.target.parent.mkdir()
        self.target.touch()
        self.run_command.return_value.stdout = 'old version without cold startup'
        with self.assertRaises(RuntimeError):
            installer.ensure_akousousin(self.app)
        self.assertEqual(self.run_command.call_count, 1)

    def test_registration_failure_is_reported(self):
        self.target.parent.mkdir()
        self.target.touch()
        self.run_command.side_effect = [subprocess.CompletedProcess([], 0, '--api-start', ''),
                                        subprocess.CompletedProcess([], 1, '', 'registration failed')]
        with self.assertRaises(RuntimeError):
            installer.ensure_akousousin(self.app)
        self.app.exit.assert_called_once()
