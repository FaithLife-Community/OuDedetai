import io
import os
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import config, wine


def make_tarball(path: Path, top: str, prefix: str = "", extra_top: str | None = None) -> Path:
    """A minimal Wine distribution: <top>/bin/wine and <top>/bin/wineserver."""
    with tarfile.open(path, "w:xz") as archive:
        for name in ("bin/wine", "bin/wineserver"):
            data = b"#!/bin/sh\n"
            info = tarfile.TarInfo(f"{prefix}{top}/{name}")
            info.size, info.mode = len(data), 0o755
            archive.addfile(info, io.BytesIO(data))
        if extra_top:
            info = tarfile.TarInfo(f"{extra_top}/README")
            archive.addfile(info, io.BytesIO(b""))
    return path


class TestExtractWineTarball(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "wine-distribution"

    def test_returns_bin_wine_of_the_extracted_distribution(self):
        top = "wine-custom_11.21_oinosrc2-x86_64"
        tarball = make_tarball(self.tmp / f"{top}.tar.xz", top)
        wine_path = wine.extract_wine_tarball(tarball, self.root)
        self.assertEqual(wine_path, self.root / "wine-custom_11.21_oinosrc2-x86_64" / "bin" / "wine")
        self.assertTrue(os.access(wine_path, os.X_OK))

    def test_accepts_dot_slash_member_names(self):
        tarball = make_tarball(self.tmp / "w.tar.xz", "wine-x", prefix="./")
        self.assertEqual(wine.extract_wine_tarball(tarball, self.root), self.root / "wine-x" / "bin" / "wine")

    def test_rejects_more_than_one_top_level_directory(self):
        tarball = make_tarball(self.tmp / "w.tar.xz", "wine-x", extra_top="other")
        with self.assertRaises(RuntimeError):
            wine.extract_wine_tarball(tarball, self.root)

    def test_keeps_other_distributions_and_replaces_its_own(self):
        wine.extract_wine_tarball(make_tarball(self.tmp / "old.tar.xz", "wine-old"), self.root)
        stale = self.root / "wine-new" / "stale-file"
        stale.parent.mkdir(parents=True)
        stale.write_text("x")
        wine.extract_wine_tarball(make_tarball(self.tmp / "new.tar.xz", "wine-new"), self.root)
        self.assertTrue((self.root / "wine-old" / "bin" / "wine").is_file())
        self.assertFalse(stale.exists())


class TestSetupWineWithChosenTarball(unittest.TestCase):
    def test_a_tarball_chosen_with_choose_file_is_extracted_and_used(self):
        tmp = Path(tempfile.mkdtemp())
        tarball = make_tarball(tmp / "wine-custom_11.21_oinosrc2-x86_64.tar.xz", "wine-custom_11.21_oinosrc2-x86_64")
        app = mock.Mock()
        app.conf.wine_binary = str(tarball)
        app.conf.wine_distribution_dir = str(tmp / "data/bin/wine-distribution")
        with mock.patch("ou_dedetai.installer.download_wine", return_value=None), \
                mock.patch("ou_dedetai.installer.create_wine_symlinks") as symlinks:
            wine.setup_wine(app)
        expected = tmp / "data/bin/wine-distribution/wine-custom_11.21_oinosrc2-x86_64/bin/wine"
        self.assertEqual(app.conf.wine_binary, str(expected))
        self.assertIsNone(app.conf.wine_appimage_path)
        symlinks.assert_called_once_with(app)

    def test_a_plain_wine_binary_is_left_alone(self):
        app = mock.Mock()
        app.conf.wine_binary = "/usr/bin/wine"
        with mock.patch("ou_dedetai.installer.download_wine", return_value=None), \
                mock.patch("ou_dedetai.installer.create_wine_symlinks"):
            wine.setup_wine(app)
        self.assertEqual(app.conf.wine_binary, "/usr/bin/wine")


class TestWinePathInDistribution(unittest.TestCase):
    def setUp(self):
        self.install_dir = Path(tempfile.mkdtemp())
        self.root = self.install_dir / "data/bin/wine-distribution"
        for name in ("wine-a-old", "wine-z-new"):
            wine.extract_wine_tarball(make_tarball(self.install_dir / f"{name}.tar.xz", name), self.root)
        # Tarballs keep their build times, so an older release has the older bin/wine
        now = time.time()
        os.utime(self.root / "wine-a-old/bin/wine", (now - 3600, now - 3600))
        os.utime(self.root / "wine-z-new/bin/wine", (now, now))
        self.conf = mock.Mock()
        self.conf.install_dir = str(self.install_dir)
        self.conf.wine_distribution_dir = str(self.root)

    def path(self) -> str:
        return config.Config.wine_path_in_distribution.fget(self.conf)

    def test_uses_the_configured_distribution_not_the_first_match(self):
        self.conf.is_wine_binary_in_distribution = True
        self.conf.wine_binary = "data/bin/wine-distribution/wine-z-new/bin/wine"
        self.assertEqual(self.path(), str(self.root / "wine-z-new/bin/wine"))
        self.conf.wine_binary = str(self.root / "wine-a-old/bin/wine")
        self.assertEqual(self.path(), str(self.root / "wine-a-old/bin/wine"))

    def test_falls_back_to_the_newest_extracted_distribution(self):
        self.conf.is_wine_binary_in_distribution = False
        self.assertEqual(self.path(), str(self.root / "wine-z-new/bin/wine"))


if __name__ == "__main__":
    unittest.main()
