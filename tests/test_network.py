import unittest
from pathlib import Path

import ou_dedetai.network as network

URLOBJ = network.UrlProps('http://ip.me')


class TestNetwork(unittest.TestCase):
    @unittest.skip('TODO')
    def test_fileprops_get_size(self):
        f = Path(__file__).parent / 'data' / 'config_empty.json'
        fo = network.FileProps(f)
        self.assertEqual(fo.size, 4)

    @unittest.skip('TODO')
    def test_fileprops_get_md5(self):
        f = Path(__file__).parent / 'data' / 'config_empty.json'
        fo = network.FileProps(f)
        self.assertEqual(fo.get_md5(), 'W3aw7vmviiMAZz4FU/YJ+Q==')

    @unittest.skip('TODO')
    def test_urlprops_get_headers(self):
        self.assertIsNotNone(URLOBJ.headers)

    @unittest.skip('TODO')
    def test_urlprops_get_headers_none(self):
        urlobj = network.UrlProps()
        self.assertIsNone(urlobj.headers)

    @unittest.skip('TODO')
    def test_urlprops_get_size(self):
        self.assertIsNotNone(URLOBJ.size)

    @unittest.skip('TODO')
    def test_urlprops_get_size_none(self):
        urlobj = network.UrlProps()
        self.assertIsNone(urlobj.size)

    @unittest.skip('TODO')
    def test_urlprops_get_md5(self):
        self.assertIsNone(URLOBJ.md5)