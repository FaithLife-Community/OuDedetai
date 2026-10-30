import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from ou_dedetai import constants, installer, runtime
from ou_dedetai.runtime_gui import RuntimePicker


class TestInstallerRuntimeRecommendation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Mock()
        self.app.conf._raw.wine_server = None
        self.app.installer_step_count = self.app.installer_step = 0
        self.app.conf.faithlife_product_version = '10'
        self.app.conf.wine_binary = constants.WINE_RECOMMENDED_SIGIL
        self.app.conf.wine_appimage_recommended_file_name = 'stable.AppImage'
        self.app.conf.wine_appimage_recommended_url = 'https://example.invalid/stable.AppImage'
        self.app.conf.wine_appimage_beta_file_name = 'beta.AppImage'
        self.app.conf.wine_appimage_beta_url = 'https://example.invalid/beta.AppImage'
        self.app.conf.download_dir = str(self.root)

    def check_default(self, desktop, command, expected):
        applications = self.root / 'applications'
        applications.mkdir(exist_ok=True)
        (applications / desktop).write_text(f'[Desktop Entry]\nExec={command}\n')
        with patch.dict(os.environ, {'XDG_DATA_DIRS': str(self.root)}), \
                patch.object(installer.system, 'run_command', return_value=Mock(stdout=desktop + '\n')), \
                patch.object(installer, 'ensure_sys_deps'), \
                patch.object(installer, 'check_opengl'), \
                patch.object(installer.utils, 'get_downloaded_file_path', return_value=None), \
                patch.object(installer.network, 'logos_reuse_download') as download:
            # Read the recommendation before install, without changing the user's selection.
            name = runtime.recommended_name(self.app)
            self.assertEqual(self.app.conf.wine_binary, constants.WINE_RECOMMENDED_SIGIL)
            installer.ensure_appimage_download(self.app)
        self.assertEqual(name, expected)
        self.assertEqual(download.call_args.args[1], name)
        self.assertEqual(self.app.conf.wine_binary, str(self.root / name))
        self.assertEqual(download.call_args.args[0], f'https://example.invalid/{name}')

    def test_native_firefox_uses_stable_for_both_installer_and_picker(self):
        self.check_default('firefox.desktop', '/usr/bin/firefox', 'stable.AppImage')

    def test_affected_browsers_still_default_to_stable(self):
        # Pre-releases are unapproved builds; #435 only warns, it doesn't switch.
        for desktop, command in [('google-chrome.desktop', '/usr/bin/google-chrome'),
                                 ('org.mozilla.firefox.desktop', '/usr/bin/flatpak run org.mozilla.firefox'),
                                 ('firefox.desktop', '/snap/bin/firefox')]:
            with self.subTest(desktop=desktop, command=command):
                self.app.conf.wine_binary = constants.WINE_RECOMMENDED_SIGIL
                self.check_default(desktop, command, 'stable.AppImage')

    def test_explicit_prerelease_choice_still_installs_prerelease(self):
        self.app.conf.wine_binary = constants.WINE_BETA_SIGIL
        with patch.object(installer, 'ensure_sys_deps'), \
                patch.object(installer, 'check_system_compatibility'), \
                patch.object(installer.network, 'logos_reuse_download') as download:
            installer.ensure_appimage_download(self.app)
        self.assertEqual(download.call_args.args[1], 'beta.AppImage')

    def test_known_bug_check_does_not_change_wine(self):
        self.app.conf.wine_binary = constants.WINE_RECOMMENDED_SIGIL
        with patch.object(installer, 'browser_affected_by_435', return_value=True):
            installer.check_for_known_bugs(self.app)
        self.assertEqual(self.app.conf.wine_binary, constants.WINE_RECOMMENDED_SIGIL)

    def test_recommendation_does_not_depend_on_current_runtime(self):
        self.app.conf.wine_binary = '/custom/wine'
        with patch.object(installer, 'default_wine_channel', return_value=constants.WINE_BETA_SIGIL), \
                patch.object(installer, 'browser_affected_by_435', return_value=True):
            self.assertEqual(runtime.recommended_name(self.app), 'beta.AppImage')
            installer.check_for_known_bugs(self.app)
        self.assertEqual(self.app.conf.wine_binary, '/custom/wine')

    def test_gui_marks_only_installer_recommendation(self):
        picker = Mock()
        picker.options = [runtime.RuntimeOption('Stable', Path('/stable.AppImage'), current=True),
                          runtime.RuntimeOption('Beta', Path('/beta.AppImage'))]
        picker.list.selection.return_value = ('0',)
        picker.list.get_children.return_value = ()
        picker.instruction_font.measure.return_value = 100
        picker.list.xview.return_value = picker.list.yview.return_value = (0, 1)
        with patch.object(installer, 'default_wine_channel', return_value=constants.WINE_BETA_SIGIL):
            picker.recommended = runtime.recommended_name(self.app)
        RuntimePicker.redraw(picker)
        self.assertFalse(picker.options[0].recommended)
        self.assertTrue(picker.options[0].current)
        self.assertTrue(picker.options[1].recommended)
        self.assertIn('(recommended)', picker.options[1].label)

    def test_install_does_not_start_while_runtime_choice_is_open(self):
        self.app._wine_selection_lock = threading.Lock()
        self.app._wine_selection_lock.acquire()
        with patch.object(installer, '_install') as install:
            installer.install(self.app)
        install.assert_not_called()
        self.app.info.assert_called_once()
        self.app._wine_selection_lock.release()

    def test_install_releases_runtime_lock_after_failure(self):
        self.app._wine_selection_lock = threading.Lock()
        with patch.object(installer, '_install', side_effect=ValueError('install failed')):
            with self.assertRaises(ValueError):
                installer.install(self.app)
        self.assertFalse(self.app._wine_selection_lock.locked())
