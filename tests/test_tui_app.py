import signal
import unittest
from unittest.mock import Mock

from ou_dedetai.tui_app import TUI


class TestSignalResize(unittest.TestCase):
    """SIGWINCH must only record the request.

    Python runs signal handlers on the main thread between bytecodes and does
    not mask the signal while its handler runs, so any real work here can be
    re-entered by the next SIGWINCH until the interpreter hits its recursion
    limit. display() picks the request up instead.
    """

    def test_signal_resize_only_sets_flag(self):
        app = Mock()
        app.resize_requested = False

        TUI.signal_resize(app, signal.SIGWINCH, None)

        self.assertTrue(app.resize_requested)
        app.resize_curses.assert_not_called()
        app.choice_q.put.assert_not_called()

    def test_signal_resize_is_reentrant(self):
        app = Mock()
        app.resize_requested = False

        # A burst of signals, as sent while dragging a window edge
        for _ in range(1000):
            TUI.signal_resize(app, signal.SIGWINCH, None)

        self.assertTrue(app.resize_requested)
        app.resize_curses.assert_not_called()

    def test_handle_resize_does_the_work(self):
        app = Mock()
        app.resize_requested = True
        app.use_python_dialog = False

        TUI.handle_resize(app)

        self.assertFalse(app.resize_requested)
        app.resize_curses.assert_called_once()
        app.choice_q.put.assert_called_once_with("resize")

    def test_handle_resize_clears_flag_before_redrawing(self):
        """A SIGWINCH arriving mid-redraw must survive as a fresh request."""
        app = Mock()
        app.resize_requested = True
        app.use_python_dialog = False

        def signal_during_redraw():
            TUI.signal_resize(app, signal.SIGWINCH, None)

        app.resize_curses.side_effect = signal_during_redraw

        TUI.handle_resize(app)

        self.assertTrue(app.resize_requested)


if __name__ == "__main__":
    unittest.main()
