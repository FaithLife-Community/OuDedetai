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
        with mock.patch.object(gui_main.MainWindow, "start_thread"), \
                mock.patch.object(gui_main.MainWindow, "_poll_logos"):
            self.window = gui_main.MainWindow(Root(), EphemeralConfiguration.load_from_path(
                os.environ["CONFIG_FILE"]), show=False)
        self.window.monitor_timer.stop()

    def tearDown(self):
        # Results still queued for this window would arrive after its temporary home is gone.
        self.window.signals.blockSignals(True)
        if self.window._refresh_later in self.window.config_updated_hooks:
            self.window.config_updated_hooks.remove(self.window._refresh_later)
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
        self.assertNotIn("Quick Start layouts", texts)  # can't be opened yet, so not shown

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


class TestBackgroundWork(GuiTestCase):
    def test_unexpected_error_is_shown(self):
        def broken():
            raise KeyError("boom")
        with mock.patch.object(QtWidgets.QMessageBox, "warning") as warning:
            thread = self.window.start_thread(broken)
            thread.join()
            self.qt.processEvents()
        warning.assert_called_once()
        self.assertIn("boom", self.window.status_gui.message_label.text())

    def test_results_arrive_through_signals(self):
        self.window.signals.integrations.emit([{"title": "Plan", "readings": [{"label": "John 1"}]}], ["Study"])
        self.qt.processEvents()
        self.assertEqual(self.window._layouts, ["Study"])
        self.assertFalse(self.window.reading_card.isHidden())

    def test_starting_logos_from_the_window_shows_the_tray(self):
        with mock.patch.object(gui_main, "TrayController") as tray, \
                mock.patch.object(self.window, "start_thread"):
            self.window.run_logos()
            tray.return_value.timer.isActive.return_value = True
            self.window.run_logos()  # one tray, however often Logos is started
        tray.assert_called_once_with(self.window, self.qt)
        self.assertFalse(self.qt.quitOnLastWindowClosed())
        self.qt.setQuitOnLastWindowClosed(True)

    def test_check_for_updates_now_clears_the_cache(self):
        with mock.patch.object(network, "is_offline", return_value=False), \
                mock.patch.object(self.window.conf._network, "clear_cache") as clear, \
                mock.patch.object(self.window, "_check_updates") as check:
            self.window._updates = {"aks": (True, "Update Akousousin to 0.9.0")}
            self.window.start_thread = lambda f: f()  # type: ignore[method-assign]
            self.window.check_updates_now()
        clear.assert_called_once()
        check.assert_called_once()
        self.assertIn("0.9.0", self.window.status_gui.message_label.text())

    def test_check_for_updates_now_does_nothing_offline(self):
        with mock.patch.object(self.window.conf._network, "clear_cache") as clear:
            self.window.check_updates_now()
        clear.assert_not_called()

    def test_desktop_integrations_update_shown(self):
        with mock.patch.object(gui_main.desktop_integrations, "is_installed", return_value=True), \
                mock.patch.object(gui_main.network, "is_offline", return_value=False):
            self.window._updates_checked({"desktop": (True, "Update the desktop integrations to 0.5.2")})
            self.assertEqual(self.window.p_desktop.text(), "Update")
            self.assertTrue(self.window.p_desktop.isEnabled())
            self.window._updates_checked({"desktop": (False, "Desktop integrations are up to date")})
            self.assertFalse(self.window.p_desktop.isEnabled())

    def test_update_button_highlights_available_updates(self):
        with mock.patch.object(gui_main.network, "is_offline", return_value=False):
            self.window._updates_checked({"aks": (True, "Update Akousousin to 0.9.0"),
                                          "wine": (False, "Wine is up to date")})
            self.assertEqual(self.window.s_update.property("kind"), "available")
            self.assertEqual(self.window.s_update.text(), "Update (1)")
            self.assertIn("Akousousin", self.window.s_update.toolTip())
            self.window._updates_checked({"aks": (False, "Akousousin is up to date")})
        self.assertIsNone(self.window.s_update.property("kind"))
        self.assertEqual(self.window.s_update.text(), "Update")

    def test_logos_state_change_redraws(self):
        with mock.patch.object(self.window, "refresh") as refresh:
            self.window._logos_state_changed(gui_main.State.RUNNING)
            self.window._logos_state_changed(gui_main.State.RUNNING)
        refresh.assert_called_once()


class TestInstalledMenus(GuiTestCase):
    installed = True

    def test_reading_plan_card_above_devotional(self):
        self.window.signals.integrations.emit([
            {"title": "Daily Devotional", "kind": "devotional", "readings": [{"label": "Day 1", "url": "x"}]},
            {"title": "Bible in a Year", "status": "On track", "progress": 0.5,
             "readings": [{"label": "Gen 1", "url": "y"}]},
        ], [])
        self.qt.processEvents()
        texts = [w.text() for w in self.window.reading_card.findChildren(QtWidgets.QLabel)]
        self.assertLess(texts.index("Reading plan"), texts.index("Today's devotional"))

    def test_run_menu_has_bible_and_blank(self):
        self.window._layouts = ["Study", "Blank"]
        menu = QtWidgets.QMenu()
        self.window._fill_run_menu(menu)
        texts = [a.text() for a in menu.actions()]
        self.assertIn("Bible (your preferred Bible)", texts)
        self.assertIn("Blank (no panels open)", texts)


class TestGuideView(GuiTestCase):
    def test_guide_closes_when_install_completes(self):
        self.window._installing = True
        self.window.show_view(gui_main.INSTALLING)
        self.window._show_status("Install Complete!", 100)
        self.assertEqual(self.window.stack.currentIndex(), gui_main.SIMPLE)
        self.assertFalse(self.window._installing)

    def test_one_progress_bar_while_installing(self):
        self.window.show_view(gui_main.INSTALLING)
        self.assertFalse(self.window.status_gui.isHidden())
        self.assertEqual(self.window.guide.findChildren(QtWidgets.QProgressBar), [])


class TestInstallGuide(unittest.TestCase):
    def setUp(self):
        gui_main._qt_app()
        self.guide = gui_main.InstallGuide()

    def test_steps_follow_installer_messages(self):
        self.guide.update_status("Ensuring wineprefix configuration…")
        self.assertEqual(self.guide.current, 6)
        self.assertEqual(self.guide.rows[0][0].text(), "✓")

    def test_unknown_message_keeps_step(self):
        self.guide.update_status("Ensuring ICU data files…")
        self.guide.update_status("Something new")
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
