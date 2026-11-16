"""control.purge: removes what Ou Dedetai put on the computer, and only that."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import constants, control


class TestPurge(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        h = self.home
        self.install = h / "share/FaithLife-Community/oudedetai"
        (self.install / "data/wine64_bottle/drive_c").mkdir(parents=True)
        apps = h / "share/applications"
        apps.mkdir(parents=True)
        for name in ("LogosBible.desktop", "oudedetai.desktop", "Logos-url-handler.desktop", "other.desktop"):
            (apps / name).write_text("[Desktop Entry]\n")
        (h / "config").mkdir()
        (h / "config/mimeapps.list").write_text(
            "[Default Applications]\nx-scheme-handler/logos4=Logos-url-handler.desktop\n"
            "text/html=firefox.desktop\nx-scheme-handler/libronixdls=Logos-url-handler.desktop\n")
        for d in ("config/FaithLife-Community", "cache/FaithLife-Community", "state/FaithLife-Community"):
            (h / d).mkdir(parents=True)
            (h / d / "file").touch()
        self.keep = h / "Documents/notes.txt"
        self.keep.parent.mkdir()
        self.keep.touch()

        self.patches = [
            mock.patch.dict(os.environ, {"HOME": str(h), "XDG_CONFIG_HOME": str(h / "config"),
                                         "XDG_DATA_HOME": str(h / "share")}),
            mock.patch.object(constants, "XDG_DATA_HOME", str(h / "share")),
            mock.patch.object(constants, "DATA_HOME", str(h / "share/FaithLife-Community")),
            mock.patch.object(constants, "CONFIG_DIR", str(h / "config/FaithLife-Community")),
            mock.patch.object(constants, "CACHE_DIR", str(h / "cache/FaithLife-Community")),
            mock.patch.object(constants, "STATE_DIR", str(h / "state/FaithLife-Community")),
            mock.patch.object(control.system, "akousousin_installed", return_value=False),
            mock.patch.object(control.system, "akousousin_launcher", return_value=h / "nothing"),
            mock.patch.object(control.shutil, "which", return_value=None),
        ]
        for p in self.patches:
            p.start()
        self.app = mock.Mock()
        self.app.conf._raw.install_dir = str(self.install)
        self.app.conf._raw.faithlife_product = "Logos"
        self.app.conf._overrides.wine_prefix = None
        self.app.conf.config_file_path = str(h / "config/FaithLife-Community/oudedetai.json")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def test_refusing_removes_nothing(self):
        self.app.approve.return_value = False
        self.assertFalse(control.purge(self.app))
        self.assertTrue(self.install.is_dir())

    def test_removes_everything_we_put_there(self):
        self.app.approve.return_value = True
        self.assertTrue(control.purge(self.app))
        h = self.home
        for gone in (self.install, h / "config/FaithLife-Community", h / "cache/FaithLife-Community",
                     h / "state/FaithLife-Community", h / "share/applications/LogosBible.desktop",
                     h / "share/applications/oudedetai.desktop",
                     h / "share/applications/Logos-url-handler.desktop"):
            self.assertFalse(gone.exists(), gone)
        self.assertTrue((h / "share/applications/other.desktop").exists())
        self.assertTrue(self.keep.exists())
        self.assertEqual((h / "config/mimeapps.list").read_text(),
                         "[Default Applications]\ntext/html=firefox.desktop\n")

    def test_warning_names_data_loss(self):
        self.app.approve.return_value = False
        control.purge(self.app)
        question, context = self.app.approve.call_args[0]
        self.assertIn("can't be undone", context)
        self.assertIn(str(self.install), context)

    def test_akousousin_purges_itself(self):
        launcher = self.home / "akousousin"
        log = self.home / "aks.log"
        launcher.write_text(f'#!/bin/sh\n[ "$1" = --help ] && echo "  --purge" && exit 0\necho "$@" >> {log}\n')
        launcher.chmod(0o755)
        with mock.patch.object(control.system, "akousousin_launcher", return_value=launcher):
            control._purge_akousousin(self.app)
        self.assertEqual(log.read_text(), "--purge --yes\n")

    def test_targets_are_not_nested(self):
        targets = control.purge_targets(self.app)
        for t in targets:
            self.assertFalse(any(p in targets for p in t.parents), t)


if __name__ == "__main__":
    unittest.main()
