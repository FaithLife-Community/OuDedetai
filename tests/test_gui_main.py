"""The Qt window: builds in both states, the Run menu, the install guide, Spanish."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from ou_dedetai import gui_main, network  # noqa: E402

from .test_wine_settings import USER_REG  # noqa: E402


class GuiTestCase(unittest.TestCase):
    installed = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {
            "HOME": self.tmp, "XDG_DATA_HOME": f"{self.tmp}/share", "XDG_STATE_HOME": f"{self.tmp}/state",
            "XDG_CONFIG_HOME": f"{self.tmp}/config", "CONFIG_FILE": f"{self.tmp}/oudedetai.json",
            "OUDEDETAI_OFFLINE": "1",
        })
        self.env.start()
        config = {}
        if self.installed:
            install = Path(self.tmp) / "LogosBible10"
            prefix = install / "data" / "wine64_bottle"
            exe = prefix / "drive_c/users/user/AppData/Local/Logos/Logos.exe"
            exe.parent.mkdir(parents=True)
            exe.touch(mode=0o755)
            (prefix / "user.reg").write_text(USER_REG)
            (prefix / "system.reg").write_text("WINE REGISTRY Version 2\n")
            config = {"faithlife_product": "Logos", "faithlife_product_version": "10",
                      "install_dir": str(install), "wine_user": "user"}
        Path(os.environ["CONFIG_FILE"]).write_text(json.dumps(config))
        from ou_dedetai.config import EphemeralConfiguration
        from ou_dedetai.gui_app import Root
        self.qt = gui_main._qt_app()
        # No background threads in tests: they'd outlive the temporary home.
        with mock.patch.object(gui_main.MainWindow, "start_thread"):
            self.window = gui_main.MainWindow(Root(), EphemeralConfiguration.load_from_path(
                os.environ["CONFIG_FILE"]), show=False)

    def tearDown(self):
        self.window.root.close()
        self.env.stop()
        network.set_offline(False)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestNotInstalled(GuiTestCase):
    def test_simple_view_offers_install(self):
        self.assertEqual(self.window.stack.currentIndex(), gui_main.SIMPLE)
        self.assertFalse(self.window.s_install_box.isHidden())
        self.assertTrue(self.window.s_run_box.isHidden())

    def test_install_disabled_while_offline(self):
        self.assertFalse(self.window.s_install.isEnabled())


class TestInstalled(GuiTestCase):
    installed = True

    def test_simple_view_offers_run_update_stop(self):
        self.assertTrue(self.window.is_installed())
        self.assertFalse(self.window.s_run_box.isHidden())
        self.assertTrue(self.window.s_run.isEnabled())
        self.assertFalse(self.window.s_stop.isEnabled())

    def test_run_menu_lists_readings_and_layouts(self):
        self.window._plans = [{"title": "Plan", "readings": [{"label": "Hebrews 9", "url": "logosref:Bible.Heb9"}]}]
        self.window._layouts = ["Sermon prep"]
        menu = QtWidgets.QMenu()
        self.window._fill_run_menu(menu)
        texts = [a.text() for a in menu.actions()]
        self.assertEqual(texts[0], "Start as usual")
        self.assertIn("Today's reading: Hebrews 9", texts)
        layouts = next(a.menu() for a in menu.actions() if a.text() == "Saved layouts")
        self.assertEqual([a.text() for a in layouts.actions()], ["Sermon prep"])
        quick = next(a.menu() for a in menu.actions() if a.text() == "Quick Start layouts")
        self.assertFalse(quick.actions()[0].isEnabled())

    def test_full_view_opens_by_setting(self):
        self.window.s_full_default.setChecked(True)
        self.assertTrue(self.window.conf.gui_full_view)

    def test_settings_page_lists_wine_settings(self):
        self.window.open_full(gui_main.SETTINGS)
        titles = [w.text() for w in self.window.pages.widget(gui_main.SETTINGS).findChildren(QtWidgets.QLabel)]
        self.assertIn("Printing through GDI", titles)
        self.assertIn("Different", titles)  # font smoothing differs in the sample user.reg

    def test_developer_options_hidden_by_default(self):
        self.window.open_full(gui_main.SETTINGS)
        self.assertTrue(self.window.dev.isHidden())
        self.window.dev_toggle.setChecked(True)
        self.assertFalse(self.window.dev.isHidden())

    def test_offline_toggle_saves_setting(self):
        os.environ.pop("OUDEDETAI_OFFLINE")
        network.set_offline(False)
        self.window.offline.setChecked(True)
        self.assertTrue(self.window.conf.offline_mode)
        self.assertTrue(network.is_offline())


class TestInstallGuide(unittest.TestCase):
    def setUp(self):
        gui_main._qt_app()
        self.guide = gui_main.InstallGuide()

    def test_steps_follow_installer_messages(self):
        self.guide.update_status("Ensuring wineprefix configuration…", 60)
        self.assertEqual(self.guide.current, 6)
        self.assertEqual(self.guide.rows[0][0].text(), "✓")
        self.assertEqual(self.guide.progress.value(), 60)

    def test_unknown_message_keeps_step(self):
        self.guide.update_status("Ensuring ICU data files…", 70)
        self.guide.update_status("Something new", 71)
        self.assertEqual(self.guide.current, 7)

    def test_every_step_has_a_title(self):
        self.assertTrue(all(title for _, title, _ in gui_main.INSTALL_STEPS))


class TestSpanish(unittest.TestCase):
    def test_spanish_translation_loads(self):
        app = gui_main._qt_app()
        translator = QtCore.QTranslator()
        folder = str(Path(gui_main.__file__).parent / "i18n")
        self.assertTrue(translator.load(QtCore.QLocale("es_ES"), "oudedetai", "_", folder))
        app.installTranslator(translator)
        try:
            self.assertEqual(gui_main.tr("Run {product}"), "Ejecutar {product}")
            self.assertEqual(gui_main.tr("Printing through GDI"), "Impresión mediante GDI")
        finally:
            app.removeTranslator(translator)


if __name__ == "__main__":
    unittest.main()
