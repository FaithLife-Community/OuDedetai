import subprocess
import unittest
from unittest.mock import patch

import ou_dedetai.system as system
from ou_dedetai.system import PackageManager


def _completed(stdout):
    """Build a CompletedProcess-like object carrying the given stdout."""
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr='')


class TestQueryPackagesVirtual(unittest.TestCase):
    """Tests for query_packages() virtual (Provides:) package handling."""

    # dpkg-query -W output: name<TAB>status<TAB>provides.
    # - libfuse2t64: installed, provides libfuse2 (the virtual package).
    # - somepkg: installed, provides two virtual names.
    # - configpkg: config-files state, must be ignored (not fully installed).
    DPKG_QUERY_STDOUT = (
        "libfuse2t64\tinstall ok installed\tlibfuse2 (= 2.9.9-9)\n"
        "somepkg\tinstall ok installed\tvirtual1, virtual2\n"
        "configpkg\tdeinstall ok config-files\tvirtual3\n"
    )

    def setUp(self):
        self.pm = PackageManager(
            install=["apt", "install", "-y"],
            download=["apt", "install", "--download-only", "-y"],
            remove=["apt", "remove", "-y"],
            query=["dpkg-query", "-W", "-f=${Package}\\t${Status}\\t${Provides}\\n"],
            query_prefix="",
            packages="libfuse2",
            incompatible_packages="",
        )

    def _fake_run_command(self, command, *args, **kwargs):
        if command[0] == 'dpkg-query':
            return _completed(self.DPKG_QUERY_STDOUT)
        raise AssertionError(f"Unexpected command: {command}")

    def test_virtual_package_satisfied(self):
        # libfuse2 is not a real package, but libfuse2t64 provides it, so it
        # must NOT be reported missing (the core bug fix).
        with patch.object(system, 'run_command', side_effect=self._fake_run_command):
            missing = system.query_packages(self.pm, ['libfuse2'], mode='install')
        self.assertEqual(missing, [])

    def test_genuinely_missing_package(self):
        # A package that is neither installed nor provided by anything must
        # still be reported missing (control case).
        with patch.object(system, 'run_command', side_effect=self._fake_run_command):
            missing = system.query_packages(self.pm, ['notarealpackage'], mode='install')
        self.assertEqual(missing, ['notarealpackage'])

    def test_directly_installed_package(self):
        # A package that IS directly installed is found by the same query.
        with patch.object(system, 'run_command', side_effect=self._fake_run_command):
            missing = system.query_packages(self.pm, ['libfuse2t64'], mode='install')
        self.assertEqual(missing, [])

    def test_virtual_package_not_conflicting_on_remove(self):
        # Virtual packages don't apply to removal: libfuse2 is not a real
        # installed package, so it must not be reported as conflicting.
        with patch.object(system, 'run_command', side_effect=self._fake_run_command):
            conflicting = system.query_packages(self.pm, ['libfuse2'], mode='remove')
        self.assertEqual(conflicting, [])

    def test_real_package_conflicting_on_remove(self):
        # A real installed package must be reported as conflicting on remove.
        with patch.object(system, 'run_command', side_effect=self._fake_run_command):
            conflicting = system.query_packages(self.pm, ['libfuse2t64'], mode='remove')
        self.assertEqual(conflicting, ['libfuse2t64'])
