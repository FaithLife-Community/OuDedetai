import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import ou_dedetai.backup as backup
from . import REPODIR
from . import TESTDATADIR


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.app.conf = Mock()

    @unittest.skip("Not tested.")
    def test_copy_data(self):
        pass

    def test_get_all_backups(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            name = 'Logos'
            self.app.conf.faithlife_product = name
            self.app.conf.backup_dir = d
            backup_dirs = []
            for n in ('1', '2', '3'):
                nd = d / f"{name}-{n}"
                nd.mkdir(parents=True)
                backup_dirs.append(str(nd))
            
            b = backup.BackupTask(self.app)
            bdirs = b._get_all_backups()
            self.assertEqual(bdirs, backup_dirs)

    def test_get_dir_group_size(self):
        size_dir = 4096

        cmd = ['du', '-sb', str(TESTDATADIR)]
        size_du = int(subprocess.check_output(cmd).decode().split()[0])
        size_testdata = size_du + size_dir  # add in 'data' dir

        cmd = ['du', '-sb', str(REPODIR / 'snap')]
        size_du = int(subprocess.check_output(cmd).decode().split()[0])
        size_snap = size_du + size_dir*3  # add in 'snap', 'bin', 'gui' dirs

        self.app.conf.backup_dir = Path('.')
        b = backup.BackupTask(self.app)
        dirs = [TESTDATADIR, REPODIR / 'snap']
        size = b._get_dir_group_size(dirs)
        self.assertEqual(size_testdata + size_snap, size)

    def test_set_dest_dir(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self.app.conf.backup_dir = d / 'backups'
            self.app.conf._logos_appdata_dir = d / 'Logos'
            b = backup.BackupTask(self.app)
            self.assertTrue(b.destination_dir)
            self.assertEqual(b.destination_dir.parent, Path(self.app.conf.backup_dir))


class TestRestore(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.app.conf = Mock()

    def test_set_dest_dir(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self.app.conf.backup_dir = d / 'backups'
            self.app.conf._logos_appdata_dir = d / 'Logos'
            self.app.conf.logos_exe = self.app.conf._logos_appdata_dir / 'Logos.exe'
            r = backup.RestoreTask(self.app)
            self.assertTrue(r.destination_dir)
            self.assertEqual(r.destination_dir, Path(self.app.conf._logos_appdata_dir))

    def test_set_src_dir(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            name = 'Logos'
            self.app.conf.faithlife_product = name
            self.app.conf.backup_dir = d / 'backups'
            nd = self.app.conf.backup_dir / f"{name}-3"
            nd.mkdir(parents=True)
            src_dir = d / 'backups' / f"{name}-3"
            self.app.conf._logos_appdata_dir = d / name
            self.app.conf.logos_exe = self.app.conf._logos_appdata_dir / f'{name}.exe'
            r = backup.RestoreTask(self.app)
            r._source_dir = src_dir
            self.assertTrue(r.source_dir)
            self.assertEqual(r.source_dir, src_dir)
