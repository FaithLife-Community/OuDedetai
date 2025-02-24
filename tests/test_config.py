import json
import shutil
import unittest
from pathlib import Path

import ou_dedetai.config as config


class TestConfigReadWrite(unittest.TestCase):
    def setUp(self):
        self.cfg = Path('tests/data/subdir/test_config.json')

    @unittest.skip('TODO')
    def test_update_config_file(self):
        config.write_config(str(self.cfg))
        config.update_config_file(str(self.cfg), 'TARGETVERSION', '100')
        with self.cfg.open() as f:
            cfg_data = json.load(f)
        self.assertEqual(cfg_data.get('TARGETVERSION'), '100')

    @unittest.skip('TODO')
    def test_write_config_parentdir(self):
        config.write_config(str(self.cfg))
        self.assertTrue(self.cfg.parent.is_dir())

    @unittest.skip('TODO')
    def test_write_config_writedata(self):
        config.write_config(str(self.cfg))
        self.assertTrue(self.cfg.read_text())

    def tearDown(self):
        shutil.rmtree(self.cfg.parent)
