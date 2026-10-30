import threading
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

from ou_dedetai.app import UserExitedFromAsk
from ou_dedetai.runtime import RuntimeOption
from ou_dedetai.runtime_gui import RuntimePicker, _PickerApp


class TestRuntimePicker(unittest.TestCase):
    def picker(self):
        picker = object.__new__(RuntimePicker)
        picker.app = Mock()
        picker.window = Mock()
        picker.list = Mock()
        picker.list.selection.return_value = ('0',)
        picker.list.get_children.return_value = ()
        picker.instruction_font = Mock()
        picker.instruction_font.measure.return_value = 100
        picker.list.xview.return_value = (0, 1)
        picker.list.yview.return_value = (0, 1)
        picker.options = [RuntimeOption('Local Wine', Path('/usr/bin/wine'))]
        picker.path = Mock()
        picker.select_button = Mock()
        picker.add_button = Mock()
        picker.cancel_button = Mock()
        picker.status = Mock()
        picker.events = Queue()
        picker.busy = False
        picker.closed = False
        picker.recommended = None
        picker.recommendation = None
        picker.releases = []
        picker.app.conf.installer_binary_dir = "/nonexistent/install/bin"
        picker.lock = threading.Lock()
        picker.lock.acquire()
        return picker

    def test_missing_row_cannot_be_selected(self):
        picker = self.picker()
        picker.options[0].path = None
        picker.highlight()
        picker.list.selection_remove.assert_called_once_with('0')
        picker.select_button.configure.assert_called_once_with(state='disabled')
        with patch.object(picker, 'work') as work:
            picker.select()
        work.assert_not_called()

    def test_add_activates_immediately(self):
        picker = self.picker()
        option = RuntimeOption('new.AppImage', Path('/Downloads/new.AppImage'))
        with patch.object(picker, 'activate') as activate:
            picker.added(option)
        activate.assert_called_once_with(option)

    def test_current_returns_without_activation(self):
        picker = self.picker()
        picker.options[0].current = True
        with patch.object(picker, 'activate') as activate:
            picker.select()
        activate.assert_not_called()
        picker.window.destroy.assert_called_once()

    def test_cancel_server_does_not_add_candidate(self):
        picker = self.picker()
        with patch.object(picker, 'choose_server', return_value=None):
            picker.added(RuntimeOption('Custom Wine', Path('/custom/wine')))
        self.assertEqual(len(picker.options), 1)

    def test_failed_selection_leaves_window_open(self):
        picker = self.picker()
        picker.busy = True
        with patch('ou_dedetai.runtime_gui.messagebox.showerror') as error:
            picker.failed(ValueError('cannot save'))
        error.assert_called_once()
        self.assertFalse(picker.busy)
        picker.window.destroy.assert_not_called()
        self.assertTrue(picker.lock.locked())

    def test_declined_confirmation_leaves_window_open_without_error(self):
        picker = self.picker()
        with patch('ou_dedetai.runtime_gui.messagebox.showerror') as error:
            picker.failed(UserExitedFromAsk())
        error.assert_not_called()
        picker.window.destroy.assert_not_called()

    def test_cannot_close_during_activation(self):
        picker = self.picker()
        picker.busy = True
        picker.close()
        picker.window.destroy.assert_not_called()
        self.assertTrue(picker.lock.locked())
        picker.activated(None)
        picker.window.destroy.assert_called_once()
        self.assertFalse(picker.lock.locked())

    def test_background_probe_preserves_highlight(self):
        picker = self.picker()
        option = picker.options[0]
        picker.version_ready(option, 'wine-10.0')
        self.assertEqual(option.version, 'wine-10.0')
        picker.list.selection_set.assert_called_once_with('0')
        picker.path.set.assert_called_with('/usr/bin/wine')

    def test_approval_is_queued_for_main_thread(self):
        picker = self.picker()
        answer = []
        worker = threading.Thread(target=lambda: answer.append(_PickerApp(picker).approve('Use version?')))
        with patch('ou_dedetai.runtime_gui.messagebox.askyesno', return_value=True) as approve:
            worker.start()
            callback = picker.events.get(timeout=2)
            approve.assert_not_called()
            callback()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(answer, [True])

    def test_recommendation_survives_both_background_completion_orders(self):
        release = ('recommended.AppImage', 'https://example.invalid/image')
        for recommendation_first in (True, False):
            with self.subTest(recommendation_first=recommendation_first):
                picker = self.picker()
                picker.options = []
                picker.list.selection.return_value = ()
                local = RuntimeOption('Local Wine', Path('/wine'), current=True)
                with patch.object(picker, 'probe'):
                    if recommendation_first:
                        picker.set_recommended(release)
                        picker.loaded([local])
                    else:
                        picker.loaded([local])
                        picker.set_recommended(release)
                self.assertEqual(len(picker.options), 2)
                self.assertTrue(picker.options[1].recommended)
                self.assertEqual(picker.options[1].download_url, release[1])

    def test_prerelease_survives_all_background_completion_orders(self):
        from itertools import permutations
        from ou_dedetai.runtime import AppImageRelease
        stable = AppImageRelease('stable.AppImage', 'https://example.invalid/stable.AppImage')
        pre = AppImageRelease('pre.AppImage', 'https://example.invalid/pre.AppImage', True)
        for order in permutations(('loaded', 'recommended', 'releases')):
            with self.subTest(order=order):
                picker = self.picker()
                picker.options = []
                picker.list.selection.return_value = ()
                local = RuntimeOption('Local Wine', Path('/wine'), current=True)
                steps = {'loaded': lambda: picker.loaded([local]),
                         'recommended': lambda: picker.set_recommended((stable.name, stable.url)),
                         'releases': lambda: picker.set_releases([stable, pre])}
                with patch.object(picker, 'probe'):
                    for step in order:
                        steps[step]()
                names = [option.name for option in picker.options]
                self.assertEqual(names, ['Local Wine', 'stable.AppImage', 'pre.AppImage'])
                self.assertTrue(picker.options[1].recommended)
                self.assertFalse(picker.options[1].prerelease)
                self.assertTrue(picker.options[2].prerelease)
                self.assertFalse(picker.options[2].recommended)
                self.assertEqual(picker.options[2].download_url, pre.url)

    def test_download_choice_is_selectable(self):
        picker = self.picker()
        option = RuntimeOption('recommended.AppImage', Path('/recommended.AppImage'),
                               recommended=True, download_url='https://example.invalid/image')
        picker.options = [option]
        picker.highlight()
        picker.select_button.configure.assert_called_with(state='normal')
        with patch.object(picker, 'work') as work, \
                patch('ou_dedetai.runtime.activate_option') as activate:
            picker.select()
            work.call_args.args[0]()
        self.assertIs(activate.call_args.args[1], option)
        self.assertTrue(picker.busy)

    def test_add_starts_in_downloads_with_appimage_filter(self):
        picker = self.picker()
        with patch('ou_dedetai.runtime.downloads_directory', return_value=Path('/home/test/Downloads')), \
                patch('ou_dedetai.runtime_gui.filedialog.askopenfilename', return_value='') as dialog, \
                patch.object(picker, 'work') as work:
            picker.add()
        self.assertEqual(dialog.call_args.kwargs['initialdir'], Path('/home/test/Downloads'))
        self.assertEqual(dialog.call_args.kwargs['filetypes'],
                         [('AppImages', ('*.AppImage', '*.appimage')), ('All files', '*')])
        work.assert_not_called()

    def test_current_row_is_bold(self):
        picker = self.picker()
        picker.options[0].current = True
        picker.redraw()
        self.assertEqual(picker.list.insert.call_args.kwargs['tags'], ('current',))
