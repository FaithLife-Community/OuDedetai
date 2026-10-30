import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from textual.app import App as TextualApp
from textual.widgets import Input, OptionList

from ou_dedetai import runtime
from ou_dedetai.app import App, UserExitedFromAsk
from ou_dedetai.tui_app import MenuModal, TextualUI, TUI
from ou_dedetai.tui_file_picker import FilePicker


class DialogTestApp(TextualApp):
    CSS = TextualUI.CSS

    def __init__(self):
        super().__init__()
        self.register_theme(TextualUI.THEMES['logos'])
        self.theme = 'logos'


class TestFilePicker(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.downloads = self.root / 'Downloads'
        self.downloads.mkdir()
        self.image = self.downloads / 'Wine [personal build].AppImage'
        self.image.touch()
        (self.downloads / 'lower.appimage').touch()
        self.wine = self.downloads / 'wine'
        self.wine.touch()
        self.folder = self.downloads / 'other builds'
        self.folder.mkdir()
        (self.folder / 'next.AppImage').touch()

    async def test_browse_and_choose_with_appimage_filter(self):
        app = DialogTestApp()
        answers = []
        async with app.run_test(size=(80, 24)) as pilot:
            picker = FilePicker('Choose Wine', self.downloads, appimages=True)
            app.push_screen(picker, answers.append)
            await pilot.pause()
            self.assertIn(self.image, picker.paths)
            self.assertIn(self.downloads / 'lower.appimage', picker.paths)
            self.assertIn(self.folder, picker.paths)
            self.assertNotIn(self.wine, picker.paths)
            menu = picker.query_one('#file-list', OptionList)
            menu.highlighted = picker.paths.index(self.folder)
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(picker.directory, self.folder)
            menu.highlighted = picker.paths.index(self.folder / 'next.AppImage')
            await pilot.click('#file-select')
            await pilot.pause()
            self.assertEqual(answers, [str(self.folder / 'next.AppImage')])

    async def test_all_files_and_parent_navigation(self):
        app = DialogTestApp()
        answers = []
        async with app.run_test(size=(80, 24)) as pilot:
            picker = FilePicker('Choose Wine', self.downloads, appimages=True)
            app.push_screen(picker, answers.append)
            await pilot.pause()
            await pilot.click('#file-filter')
            await pilot.pause()
            self.assertIn(self.wine, picker.paths)
            menu = picker.query_one('#file-list', OptionList)
            menu.highlighted = 0
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(picker.directory, self.root)
            menu.highlighted = picker.paths.index(self.downloads)
            await pilot.press('enter')
            await pilot.pause()
            menu.highlighted = picker.paths.index(self.wine)
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(answers, [str(self.wine)])

    async def test_pasted_path_and_cancel_after_invalid_path(self):
        app = DialogTestApp()
        answers = []
        async with app.run_test(size=(80, 24)) as pilot:
            picker = FilePicker('Choose Wine', self.downloads, appimages=True)
            app.push_screen(picker, answers.append)
            await pilot.pause()
            field = picker.query_one('#file-path', Input)
            field.value = '/does/not/exist'
            field.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(answers, [])
            await pilot.press('escape')
            await pilot.pause()
            self.assertEqual(answers, [None])
            picker = FilePicker('Choose Wine', self.downloads, appimages=True)
            app.push_screen(picker, answers.append)
            await pilot.pause()
            field = picker.query_one('#file-path', Input)
            field.value = str(self.image)
            field.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(answers[-1], str(self.image))

    async def test_ctrl_c_quits_like_other_dialogs(self):
        app = DialogTestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(FilePicker('Choose Wine', self.downloads, appimages=True), lambda answer: None)
            await pilot.pause()
            await pilot.press('ctrl+c')
            await pilot.pause()
        self.assertFalse(app.is_running)

    async def test_cancel_buttons_visible_and_work_on_small_terminal(self):
        for file_dialog in (False, True):
            with self.subTest(file_dialog=file_dialog):
                app = DialogTestApp()
                answers = []
                async with app.run_test(size=(80, 16)) as pilot:
                    screen = (FilePicker('Choose Wine', self.downloads, appimages=True) if file_dialog else
                              MenuModal('Select Wine runtime', ['wine ' + '/long/path' * 12] * 30))
                    app.push_screen(screen, answers.append)
                    await pilot.pause()
                    if file_dialog:
                        button = screen.query_one('#file-cancel')
                        self.assertLessEqual(button.region.bottom, 16)
                        await pilot.click('#file-cancel')
                    else:
                        button = screen.query_one('#cancel')
                        self.assertLessEqual(button.region.bottom, 16)
                        await pilot.click('#cancel')
                    await pilot.pause()
                    self.assertEqual(answers, [None if file_dialog else 'Return to Main Menu'])
                    self.assertEqual(len(app.screen_stack), 1)

    async def test_file_cancel_returns_to_runtime_menu_then_menu_cancel_exits(self):
        app = DialogTestApp()
        domain = object.__new__(TUI)
        domain.ui = app
        domain.conf = Mock()
        domain.conf._overrides.assume_yes = False
        domain._wine_selection_lock = threading.Lock()
        app.go_to_main_menu = Mock()
        with patch.object(runtime, '_ensure_stopped'), \
                patch.object(runtime, 'runtime_options', return_value=[]), \
                patch.object(runtime, 'recommended_appimage', return_value=None), \
                patch.object(runtime, 'available_appimages', return_value=[]), \
                patch.object(runtime, 'downloads_directory', return_value=self.downloads):
            async with app.run_test(size=(80, 24)) as pilot:
                worker = asyncio.create_task(asyncio.to_thread(runtime.select_runtime, domain))
                for _ in range(40):
                    await pilot.pause()
                    if isinstance(app.screen, MenuModal):
                        break
                self.assertIsInstance(app.screen, MenuModal)
                await pilot.press('enter')  # Add new is first when no runtimes are found.
                for _ in range(40):
                    await pilot.pause()
                    if isinstance(app.screen, FilePicker):
                        break
                self.assertIsInstance(app.screen, FilePicker)
                self.assertEqual(app.screen.directory, self.downloads)
                self.assertTrue(app.screen.appimages)
                await pilot.press('escape')
                for _ in range(40):
                    await pilot.pause()
                    if isinstance(app.screen, MenuModal):
                        break
                self.assertIsInstance(app.screen, MenuModal)
                self.assertFalse(worker.done())
                await pilot.press('escape')
                await asyncio.wait_for(worker, timeout=2)
                app.go_to_main_menu.assert_not_called()


class TestChooserDefaults(unittest.TestCase):
    def test_downloads_falls_back_to_home(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)):
            self.assertEqual(runtime.downloads_directory(), Path(directory))
            (Path(directory) / 'Downloads').mkdir()
            self.assertEqual(runtime.downloads_directory(), Path(directory) / 'Downloads')

    def test_cancel_after_invalid_answer_raises(self):
        app = Mock()
        app.conf._overrides.assume_yes = False
        app._exit_option = 'Exit'
        app._ask.side_effect = ['invalid', None]
        with self.assertRaises(UserExitedFromAsk):
            App.ask(app, 'Select', ['one', 'Cancel'])
        self.assertEqual(app._ask.call_count, 2)
