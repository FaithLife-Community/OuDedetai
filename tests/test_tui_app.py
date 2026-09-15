import signal
import unittest
from unittest.mock import Mock, patch

from ou_dedetai.tui_app import TUI


class TestEnd(unittest.TestCase):
    """SIGINT must only stop the loop."""

    def test_end_only_stops_the_loop(self):
        app = Mock()
        app.is_running = True

        with patch("ou_dedetai.tui_app.curses") as mock_curses:
            TUI.end(app, signal.SIGINT, None)
            mock_curses.endwin.assert_not_called()

        self.assertFalse(app.is_running)


if __name__ == "__main__":
    unittest.main()
