import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ou_dedetai import installer
from ou_dedetai import system


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
