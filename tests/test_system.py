import io
import tarfile
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ou_dedetai import system, network


class TestAkousousinInstall(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.app = Mock()
        self.app.conf.download_dir = str(self.root / 'downloads')
        Path(self.app.conf.download_dir).mkdir()
        self.app.conf.wine_prefix = str(self.root / 'prefix with spaces')
        self.app.conf.wine_binary = '/path with spaces/Wine.AppImage'
        self.app.ask.side_effect = lambda question, options: options[0]
        self.app.exit.side_effect = RuntimeError
        self.app.conf._network._repo_version.return_value = network.SoftwareReleaseInfo('beta-123', 'https://example/package')
        self.launcher = self.root / '.local/bin/akousousin'
        self.image = self.root / 'Akousousin/Akousousin-x86_64.AppImage'
        for target, kwargs in (
            ('ou_dedetai.system.constants.XDG_DATA_HOME', {'new': str(self.root)}),
            ('pathlib.Path.home', {'return_value': self.root}),
            ('ou_dedetai.system.network.logos_reuse_download', {'side_effect': self.download}),
            ('ou_dedetai.system.run_command', {'side_effect': self.run_command_stub}),
        ):
            mock = patch(target, **kwargs)
            setattr(self, target.split('.')[-1], mock.start())
            self.addCleanup(mock.stop)

    def download(self, url, filename, directory, app):
        target = Path(directory) / filename
        if filename.endswith('.tar.gz'):
            with tarfile.open(target, 'w:gz') as archive:
                script = b'#!/bin/sh\nexit 0\n'
                member = tarfile.TarInfo('Akousousin/install.sh')
                member.size = len(script)
                archive.addfile(member, io.BytesIO(script))
        else:
            target.write_bytes(b'AppImage fixture')

    def run_command_stub(self, command, **kwargs):
        if command[0] == 'sh':
            self.assertTrue(Path(command[1]).is_file())
            self.assertEqual(command[2:], ['--quiet'])
            self.launcher.parent.mkdir(parents=True)
            self.launcher.touch()
        return subprocess.CompletedProcess(command, 0, '', '')

    def assert_registration(self, executable):
        self.assertEqual(self.run_command.call_args.args[0],
                         [str(executable), '--wine-prefix', self.app.conf.wine_prefix,
                          '--wine', self.app.conf.wine_binary, '--install-only'])
        self.app.exit.assert_not_called()

    def test_default_bundle_is_installed_quietly_before_registration(self):
        system.ensure_akousousin(self.app)
        self.assertTrue(self.logos_reuse_download.call_args.args[1].endswith('Akousousin-Linux-x86_64.tar.gz'))
        self.assertEqual(self.run_command.call_count, 2)
        self.assert_registration(self.launcher)
        self.assertIn('default', self.app.ask.call_args.args[1][0])

    def test_appimage_choice_is_executable_and_registered(self):
        self.app.ask.side_effect = lambda question, options: options[1]
        system.ensure_akousousin(self.app)
        self.assertEqual(self.image.read_bytes(), b'AppImage fixture')
        self.assertEqual(self.image.stat().st_mode & 0o777, 0o755)
        self.assert_registration(self.image)
        self.assertEqual(self.run_command.call_count, 1)
        self.assertEqual(self.run_command.call_args.kwargs['env']['APPIMAGE_EXTRACT_AND_RUN'], '1')

    def test_existing_shared_installations_are_reused_without_download(self):
        for executable in (self.image, self.launcher):
            with self.subTest(executable=executable):
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.touch()
                system.ensure_akousousin(self.app)
                self.assert_registration(executable)
        self.app.conf._network._repo_version.assert_not_called()
        self.app.ask.assert_not_called()

    def test_bundle_install_failure_prevents_registration(self):
        self.run_command.side_effect = subprocess.CalledProcessError(1, ['sh'], stderr='install failed')
        with self.assertRaises(RuntimeError):
            system.ensure_akousousin(self.app)
        self.assertEqual(self.run_command.call_count, 1)
        self.app.exit.assert_called_once()

    def test_registration_failure_is_reported(self):
        self.image.parent.mkdir()
        self.image.touch()
        self.run_command.side_effect = subprocess.CalledProcessError(1, ['akousousin'], stderr='registration failed')
        with self.assertRaises(RuntimeError):
            system.ensure_akousousin(self.app)
        self.app.exit.assert_called_once()

