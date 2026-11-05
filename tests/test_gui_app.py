import threading
import unittest
from unittest.mock import Mock, patch

from ou_dedetai.gui_app import GuiApp


def _approve_on_worker(app, question):
    result = {}

    def worker():
        result["answer"] = GuiApp.approve(app, question)

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "approve() hung on worker thread"
    return result["answer"]


class TestGuiAppApprove(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        # Run scheduled callbacks immediately, standing in for the mainloop
        self.app.root.after.side_effect = lambda _delay, fn: fn()
        self.app._run_on_main_thread = lambda fn: GuiApp._run_on_main_thread(self.app, fn)

    @patch("ou_dedetai.gui_app.messagebox.askquestion", return_value="yes")
    def test_main_thread_calls_dialog_directly(self, askquestion):
        self.assertTrue(GuiApp.approve(self.app, "Q?", "ctx"))
        self.app.root.after.assert_not_called()
        askquestion.assert_called_once_with("Q?", "Q?\n\nctx")

    @patch("ou_dedetai.gui_app.messagebox.askquestion", side_effect=["yes", "no"])
    def test_worker_thread_marshals_answer(self, askquestion):
        self.assertTrue(_approve_on_worker(self.app, "Q?"))
        self.assertFalse(_approve_on_worker(self.app, "Q?"))
        self.assertEqual(self.app.root.after.call_count, 2)

    def test_run_on_main_thread_reraises_on_worker(self):
        def boom():
            raise ValueError("x")

        raised = {}

        def worker():
            try:
                GuiApp._run_on_main_thread(self.app, boom)
            except ValueError as e:
                raised["e"] = e

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5)
        self.assertFalse(t.is_alive())
        self.assertIsInstance(raised.get("e"), ValueError)


class TestGuiAppAsk(unittest.TestCase):
    def setUp(self):
        self.app = Mock()

    @patch("ou_dedetai.gui_app.ChoicePopUp")
    def test_returns_chosen_option(self, popup_cls):
        def answer(_q, _opts, answer_q):
            answer_q.put("A")
            return Mock()

        popup_cls.side_effect = answer
        self.assertEqual(GuiApp._ask(self.app, "Q?", ["A", "B"]), "A")
        self.app.root.wait_window.assert_called_once()

    @patch("ou_dedetai.gui_app.ChoicePopUp")
    def test_closed_window_returns_none(self, popup_cls):
        self.assertIsNone(GuiApp._ask(self.app, "Q?", ["A", "B"]))
        self.app.root.wait_window.assert_called_once()
