import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import Mock, patch

from ou_dedetai import installer
from ou_dedetai import system
from ou_dedetai.logos import State


class TestCheckForKnownBugs(unittest.TestCase):
    def test_no_default_browser(self):
        with tempfile.TemporaryDirectory() as data_dir:
            (Path(data_dir) / "applications").mkdir()
            result = subprocess.CompletedProcess(args=[], returncode=0, stdout="\n")
            with (
                patch.dict(os.environ, {"XDG_DATA_DIRS": data_dir}),
                patch.object(installer.system, "run_command", return_value=result),
            ):
                # Must not try to read the applications directory itself
                installer.check_for_known_bugs(Mock())


class TestCheckOpenGLVersion(unittest.TestCase):
    def test_does_not_need_wine(self):
        app = Mock()
        result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="OpenGL version string: 4.6 (Compatibility Profile)\n"
        )
        with (
            patch.object(system, "run_command", return_value=result),
            patch("ou_dedetai.wine.get_wine_env") as get_wine_env,
        ):
            supported, _ = system.check_opengl_version(app)
        self.assertTrue(supported)
        get_wine_env.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TestUpdateWineConfig(unittest.TestCase):
    def setUp(self):
        self.app = mock.Mock()
        self.app.conf.faithlife_product = "Logos"
        self.app.conf.wine64_binary = "/fake/wine64"
        self.app.is_installed.return_value = True
        self.app.logos.logos_state = State.STOPPED

    def test_apply_wine_config_leaves_renderer_alone(self):
        with mock.patch.object(installer.wine, "disable_winemenubuilder") as menu, \
                mock.patch.object(installer.wine, "set_fontsmoothing_to_rgb") as smoothing, \
                mock.patch.object(installer.wine, "configure_printing") as printing, \
                mock.patch.object(installer.wine, "set_renderer") as renderer, \
                mock.patch.object(installer.system, "ensure_akousousin") as akousousin:
            installer.apply_wine_config(self.app)
        akousousin.assert_called_once_with(app=self.app)
        printing.assert_called_once_with(app=self.app, wine64_binary="/fake/wine64")
        menu.assert_called_once_with(app=self.app, wine64_binary="/fake/wine64")
        smoothing.assert_called_once_with(app=self.app, wine64_binary="/fake/wine64")
        renderer.assert_not_called()

    def test_update_applies_config_when_logos_is_closed(self):
        with mock.patch.object(installer, "apply_wine_config") as apply:
            installer.update_wine_config(self.app)
        self.app.logos.monitor.assert_called_once()
        apply.assert_called_once_with(self.app)

    def test_update_refuses_while_logos_runs(self):
        for state in (State.STARTING, State.RUNNING):
            self.app.logos.logos_state = state
            with mock.patch.object(installer, "apply_wine_config") as apply:
                installer.update_wine_config(self.app)
            apply.assert_not_called()
            self.assertIn("Close Logos first", self.app.status.call_args.args[0])

    def test_update_does_nothing_without_an_install(self):
        self.app.is_installed.return_value = False
        with mock.patch.object(installer, "apply_wine_config") as apply:
            installer.update_wine_config(self.app)
        apply.assert_not_called()
        self.app.logos.monitor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
