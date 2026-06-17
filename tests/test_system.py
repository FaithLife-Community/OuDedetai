import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import ou_dedetai.system as system


class TestMemoryLimits(unittest.TestCase):
    """Covers the per-process memory-watchdog helpers in system.py."""

    def test_get_memory_cap_default_fraction(self):
        with patch('ou_dedetai.system.psutil.virtual_memory') as vmem:
            vmem.return_value = Mock(available=1000)
            # Default fraction is 90% of available memory.
            self.assertEqual(system.get_memory_cap(), 900)

    def test_get_memory_cap_custom_fraction(self):
        with patch('ou_dedetai.system.psutil.virtual_memory') as vmem:
            vmem.return_value = Mock(available=1000)
            self.assertEqual(system.get_memory_cap(fraction=0.5), 500)

    def test_get_memory_cap_excludes_process_rss(self):
        with patch('ou_dedetai.system.psutil.virtual_memory') as vmem:
            vmem.return_value = Mock(available=1000)
            # The process's own usage is added back before applying the fraction,
            # so its own memory doesn't count against its budget:
            # 0.9 * (1000 + 500) = 1350.
            self.assertEqual(system.get_memory_cap(process_rss=500), 1350)

    def test_get_memory_cap_returns_int(self):
        with patch('ou_dedetai.system.psutil.virtual_memory') as vmem:
            # Fractions that don't divide evenly must still yield an int (bytes).
            vmem.return_value = Mock(available=1001)
            cap = system.get_memory_cap()
            self.assertIsInstance(cap, int)
            self.assertEqual(cap, 900)

    def test_get_process_tree_rss_positive(self):
        # The current process is using some resident memory.
        self.assertGreater(system.get_process_tree_rss(os.getpid()), 0)

    def test_get_process_tree_rss_missing_pid(self):
        # A pid that doesn't exist should raise NoSuchProcess (caller handles it).
        import psutil
        # PID 0 is the scheduler and not a real selectable process.
        with self.assertRaises(psutil.Error):
            system.get_process_tree_rss(2 ** 31 - 1)

    def test_get_process_tree_rss_includes_children(self):
        # Spawn a child that allocates and touches ~100 MB, then confirm the
        # tree RSS of *this* process reflects the child's resident memory.
        # This mirrors the synthetic-hog validation of the watchdog kill path.
        baseline = system.get_process_tree_rss(os.getpid())
        hog = (
            "import sys, time\n"
            "buf = bytearray(100 * 1024 * 1024)\n"
            "for i in range(0, len(buf), 4096):\n"  # touch every page so it's resident
            "    buf[i] = 1\n"
            "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
            "time.sleep(30)\n"
        )
        child = subprocess.Popen(
            [sys.executable, '-c', hog],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            # Wait until the child reports it has finished allocating.
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            with_child = system.get_process_tree_rss(os.getpid())
            # The tree (which now includes the child) grew by most of the 100 MB.
            self.assertGreater(with_child - baseline, 50 * 1024 * 1024)
        finally:
            child.kill()
            child.wait()
            child.stdout.close()


class TestSystemdRunPrefix(unittest.TestCase):
    """Covers systemd_run_memory_prefix() and _can_use_systemd_run()."""

    def setUp(self):
        # Reset the module-level cache between tests.
        system._systemd_run_usable = None

    def tearDown(self):
        system._systemd_run_usable = None

    def test_returns_empty_when_not_usable(self):
        with patch('ou_dedetai.system._can_use_systemd_run', return_value=False):
            self.assertEqual(system.systemd_run_memory_prefix(1024), [])

    def test_returns_prefix_when_usable(self):
        with patch('ou_dedetai.system._can_use_systemd_run', return_value=True):
            prefix = system.systemd_run_memory_prefix(2 * 1024 * 1024 * 1024)
        self.assertIn('systemd-run', prefix)
        self.assertIn('--user', prefix)
        self.assertIn('--scope', prefix)
        self.assertIn('--', prefix)
        # MemoryMax must be present with the exact byte value, no swap limit.
        self.assertIn(f'MemoryMax={2 * 1024 * 1024 * 1024}', ' '.join(prefix))
        self.assertNotIn('MemorySwapMax', ' '.join(prefix))

    def test_prefix_ends_with_separator(self):
        with patch('ou_dedetai.system._can_use_systemd_run', return_value=True):
            prefix = system.systemd_run_memory_prefix(512)
        self.assertEqual(prefix[-1], '--')

    def test_can_use_systemd_run_false_when_binary_missing(self):
        with patch('ou_dedetai.system.shutil.which', return_value=None):
            self.assertFalse(system._can_use_systemd_run())

    def test_can_use_systemd_run_false_when_probe_fails(self):
        with patch('ou_dedetai.system.shutil.which', return_value='/usr/bin/systemd-run'):
            with patch('ou_dedetai.system.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=1)
                self.assertFalse(system._can_use_systemd_run())

    def test_can_use_systemd_run_caches_result(self):
        with patch('ou_dedetai.system.shutil.which', return_value='/usr/bin/systemd-run'):
            with patch('ou_dedetai.system.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)
                system._can_use_systemd_run()
                system._can_use_systemd_run()
                # Probe subprocess should only run once.
                self.assertEqual(mock_run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
