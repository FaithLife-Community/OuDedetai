import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import desktop_integrations as di
from ou_dedetai.network import SoftwareReleaseInfo


def release(version, url="https://api.github.com/repos/x/tarball/v"):
    return SoftwareReleaseInfo(version=version, download_url=url + version)


def make_app(offered=False, assume_yes=False, installed=True):
    app = mock.Mock()
    app.conf.desktop_integrations_offered = offered
    app.conf._overrides.assume_yes = assume_yes
    app.is_installed.return_value = installed
    return app


class TestSupportedDesktop(unittest.TestCase):
    def test_kde(self):
        self.assertEqual(di.supported_desktop({"XDG_CURRENT_DESKTOP": "KDE"}), di.PLASMA)

    def test_kde_in_list(self):
        self.assertEqual(di.supported_desktop({"XDG_CURRENT_DESKTOP": "ubuntu:KDE"}), di.PLASMA)

    def test_kde_full_session(self):
        self.assertEqual(di.supported_desktop({"KDE_FULL_SESSION": "true"}), di.PLASMA)

    def test_gnome(self):
        self.assertEqual(di.supported_desktop({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), di.GNOME)

    def test_other_desktops(self):
        for name in ("XFCE", "X-Cinnamon", "MATE", "Budgie:GNOME-Flashback-not", ""):
            self.assertIsNone(di.supported_desktop({"XDG_CURRENT_DESKTOP": name}), name)

    def test_unset(self):
        self.assertIsNone(di.supported_desktop({}))


class TestReleases(unittest.TestCase):
    def test_version(self):
        self.assertEqual(di.release_version("v0.5.0"), (0, 5, 0))
        self.assertEqual(di.release_version("v1.2"), (1, 2))
        self.assertEqual(di.release_version("latest"), (0,))

    def test_plasma_supported_by_every_release(self):
        self.assertTrue(di.release_supports("v0.1.0", di.PLASMA))

    def test_gnome_needs_0_5(self):
        self.assertFalse(di.release_supports("v0.4.1", di.GNOME))
        self.assertTrue(di.release_supports("v0.5.0", di.GNOME))
        self.assertTrue(di.release_supports("v0.10.0", di.GNOME))
        self.assertTrue(di.release_supports("v1.0", di.GNOME))


class TestShouldOffer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kde = {"XDG_CURRENT_DESKTOP": "KDE", "XDG_DATA_HOME": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_offers_on_kde(self):
        self.assertTrue(di.should_offer(make_app(), self.kde))

    def test_offers_on_gnome(self):
        env = dict(self.kde, XDG_CURRENT_DESKTOP="GNOME")
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
    def offer(self, app, desktop=di.PLASMA, tag="0.5.0"):
        with mock.patch.object(di, "should_offer", return_value=True), \
                mock.patch.object(di, "supported_desktop", return_value=desktop), \
                mock.patch.object(di, "latest_release", return_value=release(tag)), \
                mock.patch.object(di, "install") as install:
            di.offer(app)
        return install

    def test_declining_records_the_offer_and_installs_nothing(self):
        app = make_app()
        app.approve.return_value = False
        install = self.offer(app)
        self.assertTrue(app.conf.desktop_integrations_offered)
        install.assert_not_called()

    def test_accepting_installs(self):
        app = make_app()
        app.approve.return_value = True
        install = self.offer(app)
        install.assert_called_once_with(app)

    def test_asks_about_this_desktop(self):
        app = make_app()
        app.approve.return_value = False
        self.offer(app, desktop=di.GNOME)
        self.assertIn("GNOME", app.approve.call_args.args[0])

    def test_gnome_waits_for_a_release_that_supports_it(self):
        app = make_app()
        install = self.offer(app, desktop=di.GNOME, tag="0.4.1")
        app.approve.assert_not_called()
        install.assert_not_called()
        self.assertFalse(app.conf.desktop_integrations_offered)  # asked once it's released

    def test_gnome_without_network_asks_later(self):
        app = make_app()
        with mock.patch.object(di, "should_offer", return_value=True), \
                mock.patch.object(di, "supported_desktop", return_value=di.GNOME), \
                mock.patch.object(di, "latest_release", side_effect=RuntimeError("offline")):
            di.offer(app)
        app.approve.assert_not_called()
        self.assertFalse(app.conf.desktop_integrations_offered)

    def test_plasma_doesnt_look_up_the_release_to_ask(self):
        app = make_app()
        app.approve.return_value = False
        with mock.patch.object(di, "should_offer", return_value=True), \
                mock.patch.object(di, "supported_desktop", return_value=di.PLASMA), \
                mock.patch.object(di, "latest_release") as tag:
            di.offer(app)
        tag.assert_not_called()
        app.approve.assert_called_once()


class TestInstall(unittest.TestCase):
    def run_install(self, desktop, tag):
        """Run install() against a fake release archive; return the installer command it ran."""
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"#!/bin/sh\n"
            info = tarfile.TarInfo("logos-desktop-integrations-x/install.sh")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        app = make_app()
        result = mock.Mock(returncode=0, stdout="ok", stderr="")
        with mock.patch.object(di, "supported_desktop", return_value=desktop), \
                mock.patch.object(di, "latest_release", return_value=release(tag.lstrip("v"))), \
                mock.patch.object(di.network, "_net_get", return_value=buf.getvalue()) as get, \
                mock.patch.object(di.system, "run_command", return_value=result) as run:
            ok = di.install(app)
        if run.called:  # downloaded the release's own archive
            get.assert_called_once_with("https://api.github.com/repos/x/tarball/v" + tag.lstrip("v"))
        return ok, (run.call_args.args[0] if run.called else None), app

    def test_passes_the_desktop_to_new_installers(self):
        ok, command, _ = self.run_install(di.GNOME, "v0.5.0")
        self.assertTrue(ok)
        self.assertEqual(command[-1], "--gnome")
        ok, command, _ = self.run_install(di.PLASMA, "v0.5.0")
        self.assertEqual(command[-1], "--plasma")

    def test_older_installers_get_no_option(self):
        ok, command, _ = self.run_install(di.PLASMA, "v0.4.1")
        self.assertTrue(ok)
        self.assertTrue(command[-1].endswith("install.sh"))

    def test_gnome_refuses_a_release_without_gnome_support(self):
        ok, command, app = self.run_install(di.GNOME, "v0.4.1")
        self.assertFalse(ok)
        self.assertIsNone(command)
        self.assertIn("doesn't support GNOME yet", app.info.call_args.args[0])

    def test_other_desktops_refused(self):
        ok, command, _ = self.run_install(None, "v0.5.0")
        self.assertFalse(ok)
        self.assertIsNone(command)



class TestInstalledVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"XDG_DATA_HOME": self.tmp.name}
        (Path(self.tmp.name) / "logos-plasma").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_recorded(self):
        (Path(self.tmp.name) / "logos-plasma" / "VERSION").write_text("0.5.1\n")
        self.assertEqual(di.installed_version(self.env), "0.5.1")

    def test_before_versions_were_recorded(self):
        self.assertEqual(di.installed_version(self.env), "0")


class TestOfferUpdate(unittest.TestCase):
    def offer(self, installed="0.5.1", latest="0.5.2", skipped=None, desktop=di.PLASMA, approve=True):
        app = make_app()
        app.conf.desktop_integrations_skipped_update = skipped
        app.approve.return_value = approve
        with mock.patch.object(di, "should_offer", return_value=False), \
                mock.patch.object(di, "should_offer_update", return_value=True), \
                mock.patch.object(di, "supported_desktop", return_value=desktop), \
                mock.patch.object(di, "installed_version", return_value=installed), \
                mock.patch.object(di, "latest_release", return_value=release(latest)), \
                mock.patch.object(di, "install") as install:
            di.offer(app)
        return app, install

    def test_offers_a_newer_release(self):
        app, install = self.offer()
        self.assertIn("0.5.2", app.approve.call_args.args[0])
        install.assert_called_once_with(app)

    def test_older_installs_without_a_version_are_offered(self):
        app, install = self.offer(installed="0", latest="0.5.1")
        install.assert_called_once()

    def test_up_to_date(self):
        app, install = self.offer(installed="0.5.2", latest="0.5.2")
        app.approve.assert_not_called()

    def test_compares_numerically(self):
        app, install = self.offer(installed="0.10.0", latest="0.9.0")
        app.approve.assert_not_called()

    def test_declined_release_not_offered_again(self):
        app, install = self.offer(approve=False)
        self.assertEqual(app.conf.desktop_integrations_skipped_update, "0.5.2")
        install.assert_not_called()
        app, install = self.offer(skipped="0.5.2")
        app.approve.assert_not_called()

    def test_next_release_offered_after_declining_one(self):
        app, install = self.offer(skipped="0.5.2", latest="0.5.3")
        install.assert_called_once()

    def test_offline_does_nothing(self):
        app = make_app()
        with mock.patch.object(di, "should_offer", return_value=False), \
                mock.patch.object(di, "should_offer_update", return_value=True), \
                mock.patch.object(di, "supported_desktop", return_value=di.PLASMA), \
                mock.patch.object(di, "latest_release", side_effect=RuntimeError("offline")):
            di.offer(app)
        app.approve.assert_not_called()


class TestShouldOfferUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"XDG_CURRENT_DESKTOP": "KDE", "XDG_DATA_HOME": self.tmp.name}
        backend = Path(self.tmp.name) / "logos-plasma" / "logos_plasma.py"
        backend.parent.mkdir(parents=True)
        backend.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def test_when_installed(self):
        self.assertTrue(di.should_offer_update(make_app(), self.env))

    def test_even_after_the_install_offer(self):
        self.assertTrue(di.should_offer_update(make_app(offered=True), self.env))

    def test_not_when_assuming_yes(self):
        self.assertFalse(di.should_offer_update(make_app(assume_yes=True), self.env))

    def test_not_when_not_installed(self):
        env = dict(self.env, XDG_DATA_HOME=self.tmp.name + "/elsewhere")
        self.assertFalse(di.should_offer_update(make_app(), env))


if __name__ == "__main__":
    unittest.main()
