import tempfile
import unittest
from pathlib import Path
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


class TestNewestPublishedRelease(unittest.TestCase):
    def test_newest_skips_drafts_and_unrelated_assets(self):
        import json
        from unittest.mock import patch
        releases = [
            {'tag_name': 'draft', 'draft': True, 'published_at': '2026-11-06T00:00:00Z',
             'assets': [{'name': 'Akousousin-x86_64.AppImage', 'browser_download_url': 'draft'}]},
            {'tag_name': 'whisper', 'published_at': '2026-11-05T00:00:00Z',
             'assets': [{'name': 'whisper.tar.gz', 'browser_download_url': 'unrelated'}]},
            {'tag_name': 'older', 'published_at': '2026-11-01T00:00:00Z',
             'assets': [{'name': 'Akousousin-x86_64.AppImage', 'browser_download_url': 'older'}]},
            {'tag_name': 'newer', 'prerelease': True, 'published_at': '2026-11-04T00:00:00Z',
             'assets': [{'name': 'Akousousin-x86_64.AppImage', 'browser_download_url': 'newer'}]},
        ]
        with patch.object(network, '_net_get', return_value=json.dumps(releases).encode()):
            release = network._get_release_data('jg00dman/akousousin', name='Akousousin-x86_64.AppImage', tag='newest')
        self.assertEqual(release.download_url, 'newer')
