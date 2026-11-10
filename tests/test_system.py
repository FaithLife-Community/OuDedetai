import io
import json
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
        self.app.exit.side_effect = RuntimeError
        self.app.conf._network._repo_version.return_value = network.SoftwareReleaseInfo('beta-123', 'https://example/package')
        self.launcher = self.root / '.local/bin/akousousin'
        for target, kwargs in (
            ('pathlib.Path.home', {'return_value': self.root}),
            ('ou_dedetai.system.network.logos_reuse_download', {'side_effect': self.download}),
            ('ou_dedetai.system.run_command', {'side_effect': self.run_command_stub}),
        ):
            mock = patch(target, **kwargs)
            setattr(self, target.split('.')[-1], mock.start())
            self.addCleanup(mock.stop)

    def download(self, url, filename, directory, app):
        target = Path(directory) / filename
        self.assertTrue(filename.endswith('Akousousin-Linux-x86_64.tar.gz'))
        with tarfile.open(target, 'w:gz') as archive:
            script = b'#!/bin/sh\nexit 0\n'
            member = tarfile.TarInfo('Akousousin/install.sh')
            member.size = len(script)
            archive.addfile(member, io.BytesIO(script))

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
        self.app.conf._network._repo_version.assert_called_once_with(
            "jg00dman/akousousin", tag="published", asset_name=r"Akousousin\-Linux\-x86_64\.tar\.gz",
        )
        self.assertEqual(self.run_command.call_count, 2)
        self.assert_registration(self.launcher)
        self.app.ask.assert_not_called()

    def test_existing_shared_installation_is_reused_without_download(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.touch()
        system.ensure_akousousin(self.app)
        self.assert_registration(self.launcher)
        self.app.conf._network._repo_version.assert_not_called()
        self.app.ask.assert_not_called()

    def test_bundle_install_failure_prevents_registration(self):
        self.run_command.side_effect = subprocess.CalledProcessError(1, ['sh'], stderr='install failed')
        with self.assertRaises(RuntimeError):
            system.ensure_akousousin(self.app)
        self.assertEqual(self.run_command.call_count, 1)
        self.app.exit.assert_called_once()

    def test_registration_failure_is_reported(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.touch()
        self.run_command.side_effect = subprocess.CalledProcessError(1, ['akousousin'], stderr='registration failed')
        with self.assertRaises(RuntimeError):
            system.ensure_akousousin(self.app)
        self.app.exit.assert_called_once()


class TestPublishedAkousousinRelease(unittest.TestCase):
    def test_newest_published_release_excludes_drafts_and_accepts_stable_and_beta(self):
        def release(tag, date, prerelease=False, draft=False):
            return {"tag_name": tag, "published_at": date, "prerelease": prerelease, "draft": draft,
                    "assets": [{"name": "Akousousin-Linux-x86_64.tar.gz", "browser_download_url": f"https://x/{tag}"}]}

        stable = release("stable", "2026-11-01T00:00:00Z")
        beta = release("beta", "2026-11-02T00:00:00Z", prerelease=True)
        draft = release("draft", "2026-11-04T00:00:00Z", draft=True)
        for candidates, expected in (([draft, stable, beta], "beta"),
                                     ([beta, release("stable", "2026-11-03T00:00:00Z"), draft], "stable")):
            with self.subTest(expected=expected), patch.object(
                network, "_net_get", return_value=json.dumps(candidates).encode(),
            ) as get:
                result = network._get_release_data("jg00dman/akousousin", tag="published",
                                                   asset_name=r"Akousousin-Linux-x86_64\.tar\.gz")
                self.assertEqual(result.version, expected)
                get.assert_called_once_with("https://api.github.com/repos/jg00dman/akousousin/releases")
