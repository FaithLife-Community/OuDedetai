import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import desktop_integrations as di
from ou_dedetai import network


def make_app(offered=False, assume_yes=False, installed=True):
    app = mock.Mock()
    app.conf.desktop_integrations_offered = offered
    app.conf._overrides.assume_yes = assume_yes
    app.is_installed.return_value = installed
    return app


class TestIsKdePlasma(unittest.TestCase):
    def test_kde(self):
        self.assertTrue(di.is_kde_plasma({"XDG_CURRENT_DESKTOP": "KDE"}))

    def test_kde_in_list(self):
        self.assertTrue(di.is_kde_plasma({"XDG_CURRENT_DESKTOP": "ubuntu:KDE"}))

    def test_kde_full_session(self):
        self.assertTrue(di.is_kde_plasma({"KDE_FULL_SESSION": "true"}))

    def test_gnome(self):
        self.assertFalse(di.is_kde_plasma({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}))

    def test_unset(self):
        self.assertFalse(di.is_kde_plasma({}))


class TestShouldOffer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kde = {"XDG_CURRENT_DESKTOP": "KDE", "XDG_DATA_HOME": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_offers_on_kde(self):
        self.assertTrue(di.should_offer(make_app(), self.kde))

    def test_offers_on_gnome(self):
        env = dict(self.kde, XDG_CURRENT_DESKTOP="ubuntu:GNOME")
        self.assertTrue(di.should_offer(make_app(), env))

    def test_not_on_other_desktops(self):
        env = dict(self.kde, XDG_CURRENT_DESKTOP="XFCE")
        self.assertFalse(di.should_offer(make_app(), env))

    def test_only_once(self):
        self.assertFalse(di.should_offer(make_app(offered=True), self.kde))

    def test_not_when_assuming_yes(self):
        self.assertFalse(di.should_offer(make_app(assume_yes=True), self.kde))

    def test_not_before_logos_is_installed(self):
        self.assertFalse(di.should_offer(make_app(installed=False), self.kde))

    def test_not_when_already_installed(self):
        backend = Path(self.tmp.name) / "logos-plasma" / "logos_plasma.py"
        backend.parent.mkdir(parents=True)
        backend.touch()
        self.assertTrue(di.is_installed(self.kde))
        self.assertFalse(di.should_offer(make_app(), self.kde))


class TestOffer(unittest.TestCase):
    def test_declining_records_the_offer_and_installs_nothing(self):
        app = make_app()
        app.approve.return_value = False
        with mock.patch.object(di, "should_offer", return_value=True), \
                mock.patch.object(di, "install") as install:
            di.offer(app)
        self.assertTrue(app.conf.desktop_integrations_offered)
        install.assert_not_called()

    def test_accepting_installs(self):
        app = make_app()
        app.approve.return_value = True
        with mock.patch.object(di, "should_offer", return_value=True), \
                mock.patch.object(di, "install") as install:
            di.offer(app)
        install.assert_called_once_with(app)


if __name__ == "__main__":
    unittest.main()


class TestUpdates(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "logos-plasma"
        self.env = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.tmp.name, "XDG_CURRENT_DESKTOP": "KDE"})
        self.env.start()
        self.app = mock.Mock()
        self.app.conf._network._repo_version.return_value = network.SoftwareReleaseInfo("v0.5.2", "u")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def install(self, version=None):
        self.data.mkdir(parents=True)
        (self.data / "logos_plasma.py").touch()
        if version:
            (self.data / "VERSION").write_text(f"{version}\n")

    def test_not_installed_means_no_update(self):
        self.assertIsNone(di.installed_version())
        self.assertIsNone(di.update_available(self.app))
        self.app.conf._network._repo_version.assert_not_called()

    def test_newer_release_offered_from_the_cached_lookup(self):
        self.install("0.5.1")
        with mock.patch.object(network, "is_offline", return_value=False):
            self.assertEqual(di.update_available(self.app), "0.5.2")
        self.app.conf._network._repo_version.assert_called_once_with(di.REPOSITORY, tag="latest")

    def test_up_to_date(self):
        self.install("0.5.2")
        with mock.patch.object(network, "is_offline", return_value=False):
            self.assertIsNone(di.update_available(self.app))

    def test_install_without_a_recorded_version_counts_as_older(self):
        self.install()
        self.assertEqual(di.installed_version(), "0")
        with mock.patch.object(network, "is_offline", return_value=False):
            self.assertEqual(di.update_available(self.app), "0.5.2")

    def test_offline_never_looks(self):
        self.install("0.5.1")
        with mock.patch.object(network, "is_offline", return_value=True):
            self.assertIsNone(di.update_available(self.app))
        self.app.conf._network._repo_version.assert_not_called()

    def test_tui_notices_an_update(self):
        self.install("0.5.1")
        with mock.patch.object(di, "should_offer", return_value=False), \
                mock.patch.object(network, "is_offline", return_value=False):
            di.offer_or_notice_update(self.app)
        self.assertIn("0.5.2", self.app.status.call_args[0][0])


class TestReleaseWithoutFiles(unittest.TestCase):
    def test_source_archive_used_when_no_asset_is_named(self):
        release = {"tag_name": "v0.5.2", "assets": [], "tarball_url": "https://api.github.com/x/tarball/v0.5.2"}
        self.assertEqual(network._get_asset_url(release), release["tarball_url"])
        with self.assertRaises(ValueError):
            network._get_asset_url(release, "something.tar.gz")
