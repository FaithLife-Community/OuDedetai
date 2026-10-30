import unittest
from unittest.mock import Mock, patch
from ou_dedetai.app import UserExitedFromAsk
from ou_dedetai.tui_app import MenuModal, TUI


class TestRuntimeMenu(unittest.TestCase):
    def test_runtime_menu_runs_on_worker(self):
        app = Mock()
        with patch('ou_dedetai.runtime.select_runtime') as select:
            TUI.main_menu_select(app, 'Select Wine runtime…')
            app.start_thread.assert_called_once()
            app.start_thread.call_args.args[0]()
        select.assert_called_once_with(app)
        app._ui_call.assert_called_once_with(app.ui.go_to_main_menu)

    def test_menus_keep_their_options(self):
        # Ordinary prompts still offer Exit; the TUI only adds its usual way back.
        menu = MenuModal('Question', ['A', 'Exit', 'Return to Main Menu'])
        self.assertEqual(menu._options, ['A', 'Exit', 'Return to Main Menu'])

    def test_return_to_main_menu_from_ordinary_prompt(self):
        app = Mock()
        app._ask_modal.return_value = 'Return to Main Menu'
        self.assertIsNone(TUI._ask(app, 'Question', ['A', 'Exit']))
        self.assertEqual(app._ask_modal.call_args.args[0]._options, ['A', 'Exit', 'Return to Main Menu'])
        app.ui.call_from_thread.assert_called_once_with(app.ui.go_to_main_menu)

    def test_runtime_menu_cancel_leaves_wine_unchanged(self):
        app = Mock()
        for answer in ('Return to Main Menu', None):
            with self.subTest(answer=answer):
                app._ask_modal.return_value = answer
                with self.assertRaises(UserExitedFromAsk):
                    TUI.choose_runtime(app, 'Select Wine runtime', ['wine', 'Add new…'], 'wine')

    def test_runtime_menu_bolds_current_without_extra_items(self):
        app = Mock()
        app._ask_modal.return_value = 'other wine'
        self.assertEqual(TUI.choose_runtime(app, 'Select Wine runtime',
                                            ['current wine', 'other wine', 'Add new…'], 'current wine'), 'other wine')
        menu = app._ask_modal.call_args.args[0]
        self.assertEqual(menu._options, ['current wine', 'other wine', 'Add new…'])
        self.assertEqual(menu.current, 'current wine')

    def test_optional_runtime_menu_is_available_before_install(self):
        app = Mock()
        app.is_installed.return_value = False
        with patch('ou_dedetai.tui_app.constants.RUNMODE', 'source'):
            options = TUI.set_tui_menu_options(app)
        self.assertIn('Install', options)
        self.assertIn('Select Wine runtime…', options)
