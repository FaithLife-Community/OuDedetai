import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path
from requests.exceptions import ConnectionError as RequestsConnectionError, MissingSchema

import requests

import ou_dedetai.network as network

# Get URL object at global level so it only runs once.
URLOBJ = network.UrlProps('http://ip.me')


class TestNetwork(unittest.TestCase):
    def setUp(self):
        self.empty_json_data = '{\n}\n'

    def test_fileprops_get_size(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'file.json'
            f.write_text(self.empty_json_data)
            fo = network.FileProps(f)
            self.assertEqual(fo.size, 4)

    def test_fileprops_get_md5(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'file.json'
            f.write_text(self.empty_json_data)
            fo = network.FileProps(f)
            self.assertEqual(fo._get_md5(), 'W3aw7vmviiMAZz4FU/YJ+Q==')

    def test_urlprops_get_headers(self):
        self.assertIsNotNone(URLOBJ.headers)

    def test_urlprops_get_headers_none(self):
        test = network.UrlProps('')
        with self.assertRaises(MissingSchema):
            test.headers

    def test_urlprops_get_size(self):
        self.assertIsNotNone(URLOBJ.size)

    def test_urlprops_get_md5(self):
        self.assertIsNone(URLOBJ.md5)


class TestNetworkOffline(unittest.TestCase):
    def test_network_offline_is_connection_error(self):
        self.assertIsInstance(network.NetworkOffline(), RequestsConnectionError)

    def test_is_offline_initially_false(self):
        nr = network.NetworkRequests(force_clean=True)
        self.assertFalse(nr.is_offline)

    def test_decorator_short_circuits_when_offline(self):
        nr = network.NetworkRequests(force_clean=True)
        nr._offline_until = time.monotonic() + 60
        with self.assertRaises(network.NetworkOffline):
            nr.faithlife_product_releases("Logos", "10", "stable")

    def test_decorator_marks_offline_on_connection_error(self):
        nr = network.NetworkRequests(force_clean=True)
        with unittest.mock.patch.object(
            network,
            "_get_faithlife_product_releases",
            side_effect=requests.exceptions.ConnectionError("no internet"),
        ):
            with self.assertRaises(network.NetworkOffline):
                nr.faithlife_product_releases("Logos", "10", "stable")
        self.assertTrue(nr.is_offline)

    def test_decorator_does_not_mark_offline_on_http_error(self):
        nr = network.NetworkRequests(force_clean=True)
        with unittest.mock.patch.object(
            network,
            "_get_faithlife_product_releases",
            side_effect=requests.exceptions.HTTPError("404"),
        ):
            with self.assertRaises(requests.exceptions.HTTPError):
                nr.faithlife_product_releases("Logos", "10", "stable")
        self.assertFalse(nr.is_offline)