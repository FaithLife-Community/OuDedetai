"""Offline mode must never open a network connection."""
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import network


def _refuse(*args, **kwargs):
    raise AssertionError("tried to open a network connection in offline mode")


class TestOfflineMode(unittest.TestCase):
    def setUp(self):
        self._was = network.is_offline()
        network.set_offline(True)
        # Any attempt to connect fails the test, whatever library makes it.
        self.patches = [
            mock.patch.object(socket.socket, "connect", _refuse),
            mock.patch.object(socket, "create_connection", _refuse),
            mock.patch.object(socket, "getaddrinfo", _refuse),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        network.set_offline(self._was)

    def test_net_get_returns_nothing(self):
        app = mock.Mock()
        self.assertIsNone(network._net_get("https://api.github.com/repos/x/y/releases/latest", app=app))
        app.status.assert_called()

    def test_download_to_file_returns_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "file.bin"
            self.assertIsNone(network._net_get("https://example.com/file.bin", target))
            self.assertFalse(target.exists())

    def test_url_headers_are_empty(self):
        self.assertEqual(len(network.UrlProps("https://example.com/file.bin").headers), 0)

    def test_ensure_online_raises(self):
        with self.assertRaises(network.OfflineError):
            network._ensure_online("https://example.com")

    def test_release_lookups_fail_without_connecting(self):
        with self.assertRaises(RuntimeError):
            network._get_release_data("FaithLife-Community/OuDedetai")
        self.assertEqual(
            network._get_faithlife_product_releases("Logos", "10", "stable"), []
        )

    def test_cache_is_kept_when_stale(self):
        cache = network.CachedRequests(last_updated=0)
        with mock.patch.object(network.CachedRequests, "_write"):
            self.assertIs(cache.ensure_fresh(), cache)

    def test_offline_error_is_a_connection_error(self):
        # Existing handlers for network failures also catch offline mode.
        import requests
        self.assertTrue(issubclass(network.OfflineError, requests.exceptions.ConnectionError))


class TestOfflineSwitch(unittest.TestCase):
    def tearDown(self):
        network.set_offline(False)

    def test_environment_variable_forces_offline(self):
        with mock.patch.dict("os.environ", {"OUDEDETAI_OFFLINE": "1"}):
            network.set_offline(False)
            self.assertTrue(network.is_offline())

    def test_switch_off(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OUDEDETAI_OFFLINE", None)
            network.set_offline(True)
            network.set_offline(False)
            self.assertFalse(network.is_offline())


if __name__ == "__main__":
    unittest.main()
