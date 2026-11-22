import io
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import Mock, patch

import requests
from requests.exceptions import MissingSchema

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


class TestGetAssetUrl(unittest.TestCase):
    def setUp(self):
        self.release = {'assets': [
            {'name': 'oudedetai-arm', 'browser_download_url': 'https://x/oudedetai-arm'},
            {'name': 'oudedetai-x86_64', 'browser_download_url': 'https://x/oudedetai-x86_64'},
        ]}

    def test_selects_asset_by_name(self):
        url = network._get_asset_url(self.release, 'oudedetai-x86_64')
        self.assertEqual(url, 'https://x/oudedetai-x86_64')

    def test_raises_when_named_asset_missing(self):
        with self.assertRaises(Exception):
            network._get_asset_url(self.release, 'oudedetai')

    def test_no_name_returns_first(self):
        url = network._get_asset_url(self.release)
        self.assertEqual(url, 'https://x/oudedetai-arm')


def _response(status: int, body: bytes = b"", headers: Optional[dict] = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.raw = io.BytesIO(body)
    r.headers.update(headers or {})
    return r


def _resumable(size: int) -> requests.Response:
    return _response(200, headers={"Accept-Ranges": "bytes", "Content-Length": str(size)})


@patch.object(network.requests, "head")
@patch.object(network.requests, "get")
class TestDownloads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.app = Mock()
        self.app.exit.side_effect = SystemExit
        self.app.conf.user_download_dir = None
        self.app.conf.download_dir = str(self.dir)
        self.app.conf._network.url_size.return_value = None
        self.app.conf._network.url_md5.return_value = None

    def tearDown(self):
        self.tmp.cleanup()

    def test_head_error_yields_no_metadata(self, get, head):
        head.return_value = _response(404, headers={"Content-Length": "9"})
        self.assertIsNone(network.UrlProps("https://x/f").size)

    def test_http_error_is_not_written(self, get, head):
        head.return_value = _response(200)
        get.return_value = _response(404, b"not found")
        target = self.dir / "f"
        self.assertIsNone(network._net_get("https://x/f", target=target))
        self.assertFalse(target.exists())

    def test_ignored_range_overwrites_instead_of_appending(self, get, head):
        full = b"x" * 100  # chunk_size is size/50; keep it nonzero
        head.return_value = _resumable(len(full))
        get.return_value = _response(200, full)
        target = self.dir / "f"
        target.write_bytes(full[:40])
        self.assertTrue(network._net_get("https://x/f", target=target))
        self.assertIn("Range", get.call_args.kwargs["headers"])
        self.assertEqual(target.read_bytes(), full)

    def test_partial_content_appends(self, get, head):
        full = b"x" * 60 + b"y" * 40
        head.return_value = _resumable(len(full))
        get.return_value = _response(206, full[60:])
        target = self.dir / "f"
        target.write_bytes(full[:60])
        self.assertTrue(network._net_get("https://x/f", target=target))
        self.assertTrue(get.call_args.kwargs["headers"]["Range"].startswith("bytes=60-"))
        self.assertEqual(target.read_bytes(), full)

    def test_unsatisfiable_range_restarts(self, get, head):
        full = b"x" * 100
        head.return_value = _resumable(len(full))
        get.side_effect = [_response(416), _response(200, full)]
        target = self.dir / "f"
        target.write_bytes(full)
        self.assertTrue(network._net_get("https://x/f", target=target))
        self.assertIn("Range", get.call_args_list[0].kwargs["headers"])
        self.assertNotIn("Range", get.call_args_list[1].kwargs["headers"])
        self.assertEqual(target.read_bytes(), full)

    def test_http_error_on_resume_does_not_retry(self, get, head):
        head.return_value = _resumable(100)
        get.return_value = _response(500)
        target = self.dir / "f"
        target.write_bytes(b"x" * 40)
        self.assertIsNone(network._net_get("https://x/f", target=target))
        self.assertEqual(get.call_count, 1)

    def test_failed_download_exits_without_publishing(self, get, head):
        head.return_value = _response(200)
        get.return_value = _response(500, b"oops")
        with self.assertRaises(SystemExit):
            network.logos_reuse_download("https://x/f", "f", str(self.dir), self.app)
        self.assertFalse((self.dir / "f").exists())

    def test_bad_checksum_discards_part(self, get, head):
        head.return_value = _response(200)
        get.return_value = _response(200, b"data")
        self.app.conf._network.url_size.return_value = 99
        with self.assertRaises(SystemExit):
            network.logos_reuse_download("https://x/f", "f", str(self.dir), self.app)
        self.assertFalse((self.dir / "f").exists())
        self.assertFalse((self.dir / "f.part").exists())

    def test_success_publishes_and_copies(self, get, head):
        head.return_value = _response(200)
        get.return_value = _response(200, b"data")
        out = self.dir / "out"
        out.mkdir()
        network.logos_reuse_download("https://x/f", "f", str(out), self.app)
        self.assertEqual((self.dir / "f").read_bytes(), b"data")
        self.assertFalse((self.dir / "f.part").exists())
        self.assertEqual((out / "f").read_bytes(), b"data")
