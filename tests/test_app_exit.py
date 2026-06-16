import threading
import unittest
from unittest.mock import Mock, patch

from ou_dedetai.app import App


class _TestApp(App):
    """Minimal concrete App that skips the heavy real __init__.

    exit() only needs _threads, _pending_exit, _exit, logos and
    _schedule_exit_on_main_thread, so we wire just those up.
    """

    def __init__(self):
        self._threads = []
        self._pending_exit = None
        self.logos = Mock()
        self._exit = Mock()
        self._schedule_exit_on_main_thread = Mock()

    # Abstract methods — never exercised here, but required to instantiate.
    def _ask(self, question, options):
        raise NotImplementedError

    def _info(self, message):
        raise NotImplementedError

    def _status(self, message, percent=None):
        raise NotImplementedError


class TestAppExit(unittest.TestCase):
    def test_off_main_thread_marshals_and_does_not_tear_down(self):
        app = _TestApp()

        def worker():
            # raises SystemExit internally; the thread swallows it
            app.exit("mem cap", intended=False)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertEqual(app._pending_exit, ("mem cap", False))
        app._schedule_exit_on_main_thread.assert_called_once_with("mem cap", False)
        # The real teardown must NOT have run on the worker.
        app._exit.assert_not_called()
        app.logos.end_processes.assert_not_called()

    @patch("ou_dedetai.app.os.remove")
    @patch("ou_dedetai.app.sys.exit", side_effect=SystemExit)
    def test_on_main_thread_intended_exits_zero(self, mock_exit, mock_remove):
        app = _TestApp()
        # Record ordering of _exit vs logos.end_processes.
        manager = Mock()
        app._exit = manager._exit
        app.logos.end_processes = manager.end_processes

        with self.assertRaises(SystemExit):
            app.exit("done", intended=True)

        mock_exit.assert_called_once_with(0)
        # _exit must run before processes are ended.
        self.assertEqual(
            [c[0] for c in manager.mock_calls],
            ["_exit", "end_processes"],
        )
        app._schedule_exit_on_main_thread.assert_not_called()

    @patch("ou_dedetai.app.os.remove")
    @patch("ou_dedetai.app.sys.exit", side_effect=SystemExit)
    def test_on_main_thread_unintended_exits_one(self, mock_exit, mock_remove):
        app = _TestApp()
        with self.assertRaises(SystemExit):
            app.exit("boom", intended=False)
        mock_exit.assert_called_once_with(1)

    @patch("ou_dedetai.app.os.remove")
    @patch("ou_dedetai.app.sys.exit", side_effect=SystemExit)
    def test_on_main_thread_joins_only_non_daemon_threads(self, mock_exit, mock_remove):
        app = _TestApp()
        daemon = Mock(daemon=True)
        worker = Mock(daemon=False)
        app._threads = [daemon, worker]
        with self.assertRaises(SystemExit):
            app.exit("done", intended=True)
        worker.join.assert_called_once()
        daemon.join.assert_not_called()

    def test_default_schedule_interrupts_main(self):
        # The base default must poke the main thread.
        app = _TestApp()
        del app._schedule_exit_on_main_thread  # fall back to the real method
        with patch("_thread.interrupt_main") as mock_interrupt:
            App._schedule_exit_on_main_thread(app, "r", False)
            mock_interrupt.assert_called_once()


class TestGuiScheduleExit(unittest.TestCase):
    def test_gui_uses_root_after(self):
        from ou_dedetai.gui_app import GuiApp

        gui = GuiApp.__new__(GuiApp)  # skip __init__ (needs a real Tk root)
        gui.root = Mock()
        gui._schedule_exit_on_main_thread("reason", False)
        # Scheduled onto the mainloop with delay 0.
        self.assertEqual(gui.root.after.call_count, 1)
        self.assertEqual(gui.root.after.call_args[0][0], 0)


if __name__ == "__main__":
    unittest.main()
