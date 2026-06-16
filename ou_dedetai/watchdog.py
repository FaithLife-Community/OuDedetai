import logging
import os
import signal
import subprocess
import threading
from typing import Optional

import psutil

from ou_dedetai import system


class MemoryWatchdog:
    """Polls the RSS of tracked Wine/Logos subprocesses and hard-kills any that
    exceed 90% of currently-available system RAM.

    Has no reference to App — callers (LogosManager) read kill_reason after
    run() returns and decide how to surface the event.
    """

    def __init__(self, processes: dict, interval: float = 2):
        self._processes = processes
        self._interval = interval
        self._stop_event = threading.Event()
        self.kill_reason: Optional[str] = None

    def stop(self):
        self._stop_event.set()

    def reset(self):
        self._stop_event.clear()
        self.kill_reason = None

    def run(self):
        """Blocking loop. Returns when stopped cleanly or after killing a process."""
        while not self._stop_event.wait(self._interval):
            for name, process in list(self._processes.items()):
                if not isinstance(process, subprocess.Popen) or process.poll() is not None:
                    continue
                try:
                    rss = system.get_process_tree_rss(process.pid)
                except psutil.NoSuchProcess:
                    continue
                # Cap is 90% of memory free of this process so its own growing
                # footprint is never counted against its budget.
                cap = system.get_memory_cap(rss)
                if rss > cap:
                    display = name.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
                    logging.warning(
                        f"{display} exceeded the memory cap "
                        f"({rss // 1024 // 1024} MB > {cap // 1024 // 1024} MB); "
                        "terminating it."
                    )
                    self._hard_kill(process)
                    self.kill_reason = f"{display} used too much memory and was stopped."
                    return

    def _hard_kill(self, process: subprocess.Popen):
        """Terminates a process group, escalating to SIGKILL after a grace period."""
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
