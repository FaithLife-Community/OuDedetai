import os
import signal
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock, call, patch

import psutil

import ou_dedetai.system as system
from ou_dedetai.watchdog import MemoryWatchdog


def _baseline_python_rss() -> int:
    """Return the RSS of a freshly-started, idle Python interpreter.

    The probe process writes 'ready' before performing any user-space
    allocation so the measurement reflects interpreter startup overhead only.
    """
    probe = subprocess.Popen(
        [sys.executable, '-c',
         "import sys, time\n"
         "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
         "time.sleep(30)\n"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert probe.stdout.readline().strip() == 'ready'
        return system.get_process_tree_rss(probe.pid)
    finally:
        probe.kill()
        probe.wait()
        probe.stdout.close()


class TestMemoryWatchdogKill(unittest.TestCase):
    """Integration test: real subprocess, patched cap, real kill."""

    def test_watchdog_kills_over_limit_process(self):
        baseline_rss = _baseline_python_rss()

        # Child: signal ready (pre-allocation), allocate 50 MB touching every
        # page, signal allocated, then sleep.
        alloc_script = (
            "import sys, time\n"
            "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
            "buf = bytearray(50 * 1024 * 1024)\n"
            "for i in range(0, len(buf), 4096):\n"
            "    buf[i] = 1\n"
            "sys.stdout.write('allocated\\n'); sys.stdout.flush()\n"
            "time.sleep(30)\n"
        )
        child = subprocess.Popen(
            [sys.executable, '-c', alloc_script],
            stdout=subprocess.PIPE,
            text=True,
            # new process group so _hard_kill's killpg targets only the child
            start_new_session=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            self.assertEqual(child.stdout.readline().strip(), 'allocated')

            # Cap is just above the empty-interpreter baseline — well below the
            # child's actual RSS after allocation.
            cap = baseline_rss + 1

            processes = {'test_child': child}
            watchdog = MemoryWatchdog(processes, interval=0.05)

            with patch('ou_dedetai.watchdog.system.get_memory_cap', return_value=cap):
                t = threading.Thread(target=watchdog.run, daemon=True)
                t.start()
                t.join(timeout=5)

            self.assertFalse(t.is_alive(), "watchdog thread should have exited after kill")
            self.assertIsNotNone(child.poll(), "child process should have been killed")
            self.assertIsNotNone(watchdog.kill_reason)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
            child.stdout.close()


class TestMemoryWatchdogLogic(unittest.TestCase):
    """Unit tests for watchdog loop behaviour using mocks."""

    def _make_mock_popen(self, poll_return=None, pid=None):
        mock = Mock(spec=subprocess.Popen)
        mock.poll.return_value = poll_return
        mock.pid = pid if pid is not None else os.getpid()
        return mock

    def test_watchdog_skips_already_dead_process(self):
        dead = self._make_mock_popen(poll_return=0)
        processes = {'dead': dead}
        watchdog = MemoryWatchdog(processes, interval=0.05)

        # Stop immediately so the loop runs at most one iteration.
        watchdog.stop()
        watchdog.run()

        self.assertIsNone(watchdog.kill_reason)

    def test_watchdog_skips_no_such_process(self):
        alive = self._make_mock_popen(poll_return=None)
        processes = {'alive': alive}
        watchdog = MemoryWatchdog(processes, interval=0.05)

        with patch('ou_dedetai.watchdog.system.get_process_tree_rss',
                   side_effect=psutil.NoSuchProcess(pid=0)):
            watchdog.stop()
            watchdog.run()

        self.assertIsNone(watchdog.kill_reason)

    def test_watchdog_skips_non_popen_entry(self):
        processes = {'not_a_popen': object()}
        watchdog = MemoryWatchdog(processes, interval=0.05)
        watchdog.stop()
        watchdog.run()
        self.assertIsNone(watchdog.kill_reason)

    def test_stop_exits_loop(self):
        watchdog = MemoryWatchdog({}, interval=0.05)
        t = threading.Thread(target=watchdog.run, daemon=True)
        t.start()
        watchdog.stop()
        t.join(timeout=2)
        self.assertFalse(t.is_alive())

    def test_reset_clears_state(self):
        watchdog = MemoryWatchdog({}, interval=0.05)
        watchdog.kill_reason = "something"
        watchdog._stop_event.set()

        watchdog.reset()

        self.assertIsNone(watchdog.kill_reason)
        self.assertFalse(watchdog._stop_event.is_set())


class TestHardKill(unittest.TestCase):
    """Unit tests for _hard_kill SIGTERM/SIGKILL escalation."""

    def _watchdog(self):
        return MemoryWatchdog({})

    def test_hard_kill_sigterm_success(self):
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = os.getpid()
        mock_process.wait.return_value = None

        with patch('ou_dedetai.watchdog.os.killpg') as mock_killpg:
            self._watchdog()._hard_kill(mock_process)

        calls = mock_killpg.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], call(mock_process.pid, signal.SIGTERM))

    def test_hard_kill_escalates_to_sigkill(self):
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = os.getpid()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd='', timeout=10)

        with patch('ou_dedetai.watchdog.os.killpg') as mock_killpg:
            self._watchdog()._hard_kill(mock_process)

        calls = mock_killpg.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], call(mock_process.pid, signal.SIGTERM))
        self.assertEqual(calls[1], call(mock_process.pid, signal.SIGKILL))


if __name__ == '__main__':
    unittest.main()
