import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ou_dedetai import installer


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


if __name__ == "__main__":
    unittest.main()
