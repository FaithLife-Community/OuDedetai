import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import desktop_integrations as di


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

    def test_not_on_gnome(self):
        env = dict(self.kde, XDG_CURRENT_DESKTOP="GNOME")
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
