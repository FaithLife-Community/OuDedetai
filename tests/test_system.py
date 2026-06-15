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


if __name__ == '__main__':
    unittest.main()
