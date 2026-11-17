import subprocess
import unittest
from unittest import mock

from ou_dedetai import wine


class TestWineserverHelpers(unittest.TestCase):
    def setUp(self):
        self.app = mock.Mock()
        self.app.conf.wineserver_binary = "/fake/wineserver"

    def test_wait_runs_only_wineserver_w(self):
        # A bare "wineserver" first would start a server that never exits, and -w would hang
        with mock.patch.object(wine, "run_wine_during_install") as run:
            wine.wineserver_wait(self.app)
        run.assert_called_once_with(self.app, "/fake/wineserver", exe_args=["-w"])

    def test_kill_runs_only_wineserver_k_and_tolerates_no_server(self):
        error = subprocess.CalledProcessError(1, "wineserver -k")
        with mock.patch.object(wine, "run_wine_during_install", side_effect=error) as run:
            wine.wineserver_kill(self.app)  # must not raise
        run.assert_called_once_with(self.app, "/fake/wineserver", exe_args=["-k"])

    def test_wait_failure_is_not_fatal(self):
        error = subprocess.CalledProcessError(2, "wineserver -w")
        with mock.patch.object(wine, "run_wine_during_install", side_effect=error):
            wine.wineserver_wait(self.app)


if __name__ == "__main__":
    unittest.main()
