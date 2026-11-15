import threading
import unittest
from unittest.mock import Mock, patch

from ou_dedetai.gui_app import GuiApp, GuiBridge, QtWidgets


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
        self.app._is_gui_thread.side_effect = lambda: threading.current_thread() is threading.main_thread()
        self.app._dispatch = lambda fn, wait=True: GuiApp._dispatch(self.app, fn, wait)
        self.app._bridge.invoke.emit.side_effect = lambda request: GuiBridge._run(None, request)

    @patch("ou_dedetai.gui_app.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.StandardButton.Yes)
    def test_main_thread_calls_dialog_directly(self, askquestion):
        self.assertTrue(GuiApp.approve(self.app, "Q?", "ctx"))
        self.app._bridge.invoke.emit.assert_not_called()
        self.assertEqual(askquestion.call_args.args[:3], (self.app.root, "Q?", "Q?\n\nctx"))

    @patch("ou_dedetai.gui_app.QtWidgets.QMessageBox.question",
           side_effect=[QtWidgets.QMessageBox.StandardButton.Yes, QtWidgets.QMessageBox.StandardButton.No])
    def test_worker_thread_marshals_answer(self, askquestion):
        self.assertTrue(_approve_on_worker(self.app, "Q?"))
        self.assertFalse(_approve_on_worker(self.app, "Q?"))
        self.assertEqual(self.app._bridge.invoke.emit.call_count, 2)

    def test_run_on_main_thread_reraises_on_worker(self):
        def boom():
            raise ValueError("x")

        raised = {}

        def worker():
            try:
                GuiApp._dispatch(self.app, boom)
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
        self.app._dispatch.side_effect = lambda fn: fn()

    @patch("ou_dedetai.gui_app.ChoicePopUp")
    def test_returns_chosen_option(self, popup_cls):
        popup_cls.return_value.get_answer.return_value = "A"
        self.assertEqual(GuiApp._ask(self.app, "Q?", ["A", "B"]), "A")
        self.app._dispatch.assert_called_once()

    @patch("ou_dedetai.gui_app.ChoicePopUp")
    def test_closed_window_returns_none(self, popup_cls):
        popup_cls.return_value.get_answer.return_value = None
        self.assertIsNone(GuiApp._ask(self.app, "Q?", ["A", "B"]))
        self.app._dispatch.assert_called_once()
