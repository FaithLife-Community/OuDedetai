import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import control


class TestRemoveIndexFiles(unittest.TestCase):
    def test_keeps_library_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "Data" / "abc123"
            folders = ["BibleIndex", "LibraryIndex", "PersonalBookIndex", "LibraryCatalog"]
            for folder in folders:
                (data / folder).mkdir(parents=True)
                (data / folder / "file.db").write_text("x")
            app = mock.Mock()
            app.conf.logos_exe = os.path.join(tmp, "Logos.exe")

            control.remove_all_index_files(app)

            for folder in folders[:3]:
                self.assertEqual(list((data / folder).iterdir()), [], folder)
            # the indexer needs the catalog to know which resources to index
            self.assertTrue((data / "LibraryCatalog" / "file.db").exists())


if __name__ == "__main__":
    unittest.main()
