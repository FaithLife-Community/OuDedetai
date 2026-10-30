import unittest
from unittest.mock import Mock, patch
from ou_dedetai import constants
from ou_dedetai.gui_app import ControlWindow, GuiApp


class TestRuntimeMenu(unittest.TestCase):
    def test_selection_is_available_for_system_wine(self):
        window = Mock()
        window.is_installed.return_value = True
        window.conf._raw.wine_binary_code = 'System'
        window.conf._raw.wine_binary = '/usr/bin/wine'
        with patch('ou_dedetai.gui_app.gui.ToolTip'):
            ControlWindow.update_latest_appimage_button(window)
        window.gui.set_appimage_button.state.assert_called_once_with(['!disabled'])

    def test_picker_opens_on_tk_thread(self):
        window = Mock()
        with patch('ou_dedetai.runtime_gui.RuntimePicker') as picker:
            ControlWindow.set_appimage(window)
        picker.assert_called_once_with(window)
        window.start_thread.assert_not_called()

    def test_file_dialog_cancel_is_cancel(self):
        with patch('ou_dedetai.gui_app.fd.askopenfilename', return_value=''):
            self.assertIsNone(GuiApp._ask(Mock(), 'Choose runtime', constants.PROMPT_OPTION_FILE))

    def test_selection_is_available_before_install(self):
        window = Mock()
        window.is_installed.return_value = False
        with patch('ou_dedetai.gui_app.gui.ToolTip'):
            ControlWindow.update_latest_appimage_button(window)
        window.gui.set_appimage_button.state.assert_called_once_with(['!disabled'])
        window.gui.latest_appimage_button.state.assert_called_once_with(['disabled'])
