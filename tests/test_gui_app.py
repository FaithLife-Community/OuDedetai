import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ou_dedetai.gui_app import ControlWindow, InstallerWindow


class TestRunnerSelection(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(ControlWindow)
        self.app.root = Mock()
        self.app.conf = SimpleNamespace(wine_binary='/old/wine')

    @patch('ou_dedetai.gui_app.utils.get_wine_options', return_value=['Recommended Bundled'])
    def test_shared_options(self, options):
        self.assertEqual(self.app.runner_options(), ['Recommended Bundled', self.app._runner_file_option])
        window = object.__new__(InstallerWindow)
        window.app, window.conf = self.app, self.app.conf
        window.gui = Mock()
        window.gui.winevar.get.return_value = 'Recommended Bundled'
        window._post_dropdown_change = Mock()
        window.set_wine()
        self.assertEqual(self.app.conf.wine_binary, 'Recommended Bundled')
        window._post_dropdown_change.assert_called_once()

    @patch('ou_dedetai.gui_app.fd.askopenfilename', return_value='')
    def test_cancel_file_preserves_selection(self, dialog):
        self.assertFalse(self.app.select_runner(self.app._runner_file_option))
        self.assertEqual(self.app.conf.wine_binary, '/old/wine')

    @patch('ou_dedetai.gui_app.messagebox.showerror')
    @patch('ou_dedetai.gui_app.utils.check_appimage', return_value=False)
    @patch('ou_dedetai.gui_app.tarfile.is_tarfile', return_value=False)
    @patch('ou_dedetai.gui_app.fd.askopenfilename', return_value='/invalid.tar.gz')
    def test_invalid_file_preserves_selection(self, dialog, archive, image, error):
        self.assertFalse(self.app.select_runner(self.app._runner_file_option))
        self.assertEqual(self.app.conf.wine_binary, '/old/wine')
        error.assert_called_once()

    @patch('ou_dedetai.gui_app.utils.check_appimage', return_value=False)
    @patch('ou_dedetai.gui_app.tarfile.is_tarfile', return_value=True)
    @patch('ou_dedetai.gui_app.fd.askopenfilename', return_value='/custom.tar.gz')
    def test_select_local_tarball(self, dialog, archive, image):
        self.assertTrue(self.app.select_runner(self.app._runner_file_option))
        self.assertEqual(self.app.conf.wine_binary, '/custom.tar.gz')

    @patch('ou_dedetai.gui_app.system.ensure_winetricks')
    @patch('ou_dedetai.gui_app.wine.setup_wine')
    def test_installed_runner_uses_shared_selection_and_setup(self, setup, winetricks):
        self.app._ask = Mock(return_value='Recommended Bundled')
        self.app.runner_options = Mock(return_value=['Recommended Bundled'])
        self.app.update_latest_appimage_button = Mock()
        self.app.set_runner()
        self.app._ask.assert_called_once_with('Select Runner', self.app.runner_options())
        self.assertEqual(self.app.conf.wine_binary, 'Recommended Bundled')
        setup.assert_called_once_with(self.app)
        winetricks.assert_called_once_with(self.app)
