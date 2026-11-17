import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import config, wine


def make_tarball(path: Path, top: str) -> Path:
    """A minimal Wine distribution: <top>/bin/wine and <top>/bin/wineserver."""
    with tarfile.open(path, "w:xz") as archive:
        for name in ("bin/wine", "bin/wineserver"):
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size, info.mode = 10, 0o755
            archive.addfile(info, io.BytesIO(b"#!/bin/sh\n"))
    return path


class TestSetupWineWithTarballs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app = mock.Mock()
        self.app.conf.wine_distribution_dir = str(self.tmp / "data/bin/wine-distribution")

    def run_setup_wine(self, downloaded=None):
        with mock.patch("ou_dedetai.installer.download_wine", return_value=downloaded), \
                mock.patch("ou_dedetai.installer.create_wine_symlinks") as symlinks:
            wine.setup_wine(self.app)
        symlinks.assert_called_once_with(self.app)

    def test_a_tarball_chosen_with_choose_file_is_unpacked_and_used(self):
        top = "wine-custom_11.22_oinos-pre-x-x86_64"
        self.app.conf.wine_binary = str(make_tarball(self.tmp / f"{top}.tar.xz", top))
        self.run_setup_wine()
        self.assertEqual(self.app.conf.wine_binary, str(self.tmp / "data/bin/wine-distribution" / top / "bin/wine"))
        self.assertIsNone(self.app.conf.wine_appimage_path)

    def test_the_newly_unpacked_build_is_used_not_an_older_one(self):
        root = Path(self.app.conf.wine_distribution_dir)
        (root / "wine-a-older/bin").mkdir(parents=True)
        (root / "wine-a-older/bin/wine").write_text("")
        self.app.conf.wine_binary = "/usr/bin/wine"
        self.run_setup_wine(make_tarball(self.tmp / "wine-z-new.tar.xz", "wine-z-new"))
        self.assertEqual(self.app.conf.wine_binary, str(root / "wine-z-new/bin/wine"))

    def test_a_plain_wine_binary_is_left_alone(self):
        self.app.conf.wine_binary = "/usr/bin/wine"
        self.run_setup_wine()
        self.assertEqual(self.app.conf.wine_binary, "/usr/bin/wine")


class TestWinePathInDistribution(unittest.TestCase):
    def test_uses_the_configured_build_not_the_first_unpacked_one(self):
        root = Path(tempfile.mkdtemp())
        for name in ("wine-a-old", "wine-z-new"):
            (root / name / "bin").mkdir(parents=True)
            (root / name / "bin/wine").write_text("")
        conf = mock.Mock()
        conf.wine_distribution_dir = str(root)
        conf.is_wine_binary_in_distribution = True
        conf.wine_binary = str(root / "wine-z-new/bin/wine")
        self.assertEqual(config.Config.wine_path_in_distribution.fget(conf), str(root / "wine-z-new/bin/wine"))


if __name__ == "__main__":
    unittest.main()
