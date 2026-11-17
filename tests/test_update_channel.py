"""Releases / Prereleases: one choice for Ou Dedetai and Wine updates."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import config, constants, installer, network, utils


def fake_conf(chosen=False, app_channel="stable", wine_channel="stable"):
    conf = mock.Mock()
    conf._raw = config.PersistentConfiguration()
    conf._raw.update_channel_chosen = chosen
    conf._raw.app_release_channel = app_channel
    conf._raw.wine_release_channel = wine_channel
    return conf


class TestDefault(unittest.TestCase):
    def test_a_development_build_follows_prereleases_until_the_user_chooses(self):
        conf = fake_conf()
        with mock.patch.object(constants, "LLI_CURRENT_VERSION", "4.0.0-beta.19.dev3"):
            config.Config._default_to_prereleases(conf)
        self.assertEqual((conf._raw.app_release_channel, conf._raw.wine_release_channel), ("dev", "dev"))

    def test_the_users_choice_sticks(self):
        conf = fake_conf(chosen=True)
        with mock.patch.object(constants, "LLI_CURRENT_VERSION", "4.0.0-beta.19.dev3"):
            config.Config._default_to_prereleases(conf)
        self.assertEqual(conf._raw.app_release_channel, "stable")

    def test_a_release_build_keeps_its_channel(self):
        conf = fake_conf()
        with mock.patch.object(constants, "LLI_CURRENT_VERSION", "4.0.0-beta.19"):
            config.Config._default_to_prereleases(conf)
        self.assertEqual(conf._raw.app_release_channel, "stable")

    def test_choosing_sets_both_and_remembers(self):
        conf = fake_conf()
        config.Config.update_channel.fset(conf, "dev")
        self.assertEqual((conf._raw.app_release_channel, conf._raw.wine_release_channel), ("dev", "dev"))
        self.assertTrue(conf._raw.update_channel_chosen)
        conf._write.assert_called_once()


class TestVersions(unittest.TestCase):
    def test_prerelease_channel_follows_oudedetai_prereleases(self):
        requests = network.NetworkRequests.__new__(network.NetworkRequests)
        with mock.patch.object(network.NetworkRequests, "_repo_version") as repo, \
                mock.patch("ou_dedetai.system.get_architecture", return_value=("x86_64", 64)):
            requests.app_latest_version("dev")
        self.assertEqual(repo.call_args.args[0], "FaithLife-Community/OuDedetai")
        self.assertEqual(repo.call_args.kwargs["tag"], "prerelease")

    def test_dev_builds_sit_between_beta_18_and_beta_19(self):
        from packaging.version import Version
        self.assertLess(Version("4.0.0-beta.18"), Version("4.0.0-beta.19.dev1"))
        self.assertLess(Version("4.0.0-beta.19.dev9"), Version("4.0.0-beta.19"))

    def test_version_read_from_a_binary_keeps_dev(self):
        with tempfile.TemporaryDirectory() as d:
            binary = Path(d) / "oudedetai"
            binary.write_text("#!/bin/sh\necho 'Ou Dedetai, 4.0.0-beta.19.dev12 by FaithLife Community'\n")
            self.assertEqual(utils.get_lli_release_version(binary), "4.0.0-beta.19.dev12")


class TestReplaceInstalled(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.launcher = self.dir / "oudedetai"
        self.launcher.write_text("old")
        self.running = self.dir / "Downloads-oudedetai"
        self.running.write_text("new")
        self.app = mock.Mock()
        self.app.conf._raw.install_dir = str(self.dir)
        self.app.conf.install_dir = str(self.dir)
        self.patches = [
            mock.patch.object(constants, "RUNMODE", "binary"),
            mock.patch.object(constants, "LLI_CURRENT_VERSION", "4.0.0-beta.19.dev5"),
            mock.patch.object(installer.sys, "executable", str(self.running)),
            mock.patch.object(installer, "create_launcher_shortcuts"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def replace(self, installed, approve=True):
        self.app.approve.return_value = approve
        with mock.patch.object(installer.utils, "get_lli_release_version", return_value=installed):
            return installer.offer_to_replace_installed(self.app)

    def test_newer_build_replaces_the_installed_copy_when_agreed(self):
        self.assertTrue(self.replace("4.0.0-beta.15"))
        self.assertEqual(self.launcher.read_text(), "new")
        installer.create_launcher_shortcuts.assert_called_once()

    def test_declined(self):
        self.assertFalse(self.replace("4.0.0-beta.15", approve=False))
        self.assertEqual(self.launcher.read_text(), "old")

    def test_never_goes_back(self):
        self.assertFalse(self.replace("4.0.0-beta.19.dev9"))
        self.app.approve.assert_not_called()
        self.assertEqual(self.launcher.read_text(), "old")

    def test_running_the_installed_copy_asks_nothing(self):
        with mock.patch.object(installer.sys, "executable", str(self.launcher)):
            self.assertFalse(self.replace("4.0.0-beta.15"))
        self.app.approve.assert_not_called()


class TestAppImageInstallsOnPrereleases(unittest.TestCase):
    """An install upgraded from beta 15 (Wine 10.8 AppImage) is offered the oinos tarball."""

    def conf(self, channel):
        conf = mock.Mock()
        conf.wine_binary = "/x/data/bin/wine-staging_10.8-x86_64.AppImage"
        conf.is_wine_binary_in_distribution = False
        conf.wine_release_channel = channel
        conf._wine_tarball_release.version = "11.22-oinos-pre-b1e3dff"
        conf.wine_download_file_name = "wine-staging_10.8-x86_64.AppImage"
        return conf

    def test_prereleases_recommend_oinos(self):
        self.assertEqual(config.Config.wine_recommended_version.fget(self.conf("dev")), "11.22")

    def test_releases_keep_the_appimage(self):
        self.assertEqual(config.Config.wine_recommended_version.fget(self.conf("stable")), "10.8")

    def test_update_moves_the_appimage_install_onto_the_tarball(self):
        app = mock.Mock()
        app.conf.wine_appimage_path = "/x/wine.AppImage"
        app.conf.wine_release_channel = "dev"
        with mock.patch.object(installer, "setup_wine"):
            installer.update_to_latest_wine(app)
        self.assertEqual(app.conf.wine_binary, constants.WINE_RECOMMENDED_TARBALL_SIGIL)
        self.assertIsNone(app.conf.wine_appimage_path)
        app.conf.wine_release_channel = "stable"
        app.conf.wine_appimage_path = "/x/wine.AppImage"
        with mock.patch.object(installer, "setup_wine"):
            installer.update_to_latest_wine(app)
        self.assertEqual(app.conf.wine_binary, constants.WINE_RECOMMENDED_APPIMAGE_SIGIL)
