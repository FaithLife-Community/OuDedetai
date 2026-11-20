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
            check.return_value = {"aks": (True, "Update Akousousin to 0.9.0")}
            self.window._updates = {}  # the signal hasn't reached the window yet
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

    def test_tray_quit_warns_while_logos_runs(self):
        qt = mock.Mock()
        tray = gui_main.TrayController(self.window, qt)
        self.window.logos.logos_state = gui_main.State.RUNNING
        with mock.patch.object(QtWidgets.QMessageBox, "exec"), \
                mock.patch.object(QtWidgets.QMessageBox, "clickedButton", return_value=None):
            tray.quit()  # Cancel
        qt.quit.assert_not_called()
        self.window.logos.logos_state = gui_main.State.STOPPED
        tray.quit()
        qt.quit.assert_called_once()

    def test_stop_waits_politely_and_force_needs_a_yes(self):
        done = mock.Mock()
        with mock.patch.object(self.window, "start_thread"):
            self.window.stop_logos(on_closed=done)
        dialog = self.window._close_dialog
        dialog._show_progress(True, 0)
        self.assertIn("syncing", dialog.text.text())
        dialog._show_progress(False, 30)
        self.assertIn("asking you something", dialog.text.text())
        with mock.patch.object(QtWidgets.QMessageBox, "warning",
                               return_value=QtWidgets.QMessageBox.StandardButton.Cancel), \
                mock.patch.object(self.window, "start_thread") as start:
            dialog._force()
        start.assert_not_called()  # no force without a yes
        done.assert_not_called()
        dialog._done(True)  # Logos closed by itself
        done.assert_called_once()

    def test_force_after_yes(self):
        with mock.patch.object(self.window, "start_thread"):
            self.window.stop_logos()
        dialog = self.window._close_dialog
        with mock.patch.object(QtWidgets.QMessageBox, "warning",
                               return_value=QtWidgets.QMessageBox.StandardButton.Yes), \
                mock.patch.object(self.window, "start_thread") as start:
            dialog._force()
        start.assert_called_once_with(self.window.logos.force_close)
        self.assertTrue(dialog.cancelled)

    def test_choose_a_wine_build_offers_our_bundles_and_a_file(self):
        menu = self.window.wine_build_actions["dev"].associatedObjects()[0]
        texts = [a.text() for a in menu.actions() if a.text()]
        self.assertEqual(texts, ["Newest prerelease", "Newest release",
                                 "A file on this computer (AppImage or tarball)…"])
        with mock.patch.object(gui_main.utils, "installed_wine_build_name",
                               return_value="wine-custom_11.22_oinos-pre-b1e3dff-x86_64"):
            self.window._show_wine_builds({
                "dev": ("11.22-oinos-pre-b1e3dff", "wine-custom_11.22_oinos-pre-b1e3dff-x86_64"),
                "stable": ("11.21-logoswt20261103", "wine-custom_11.21_logoswt20261103-x86_64")})
        self.assertEqual(self.window.wine_build_actions["dev"].text(),
                         "Newest prerelease: 11.22-oinos-pre-b1e3dff (in use)")
        self.assertEqual(self.window.wine_build_actions["stable"].text(), "Newest release: 11.21-logoswt20261103")

    def test_switching_to_a_bundle_needs_logos_closed_and_a_yes(self):
        self.window.logos.logos_state = gui_main.State.RUNNING
        with mock.patch.object(self.window, "approve") as approve:
            self.window.use_wine_release("stable")
        approve.assert_not_called()
        self.window.logos.logos_state = gui_main.State.STOPPED
        with mock.patch.object(self.window, "approve", return_value=True), \
                mock.patch.object(self.window, "start_thread", side_effect=lambda f: f()), \
                mock.patch.object(gui_main.installer, "use_wine_release") as use, \
                mock.patch.object(self.window, "_check_updates"):
            self.window.use_wine_release("stable")
        use.assert_called_once_with(self.window, "stable")

    def test_updates_choice_sets_both_channels(self):
        with mock.patch.object(self.window, "start_thread"):
            self.window.s_prereleases.setChecked(True)
        self.assertEqual(self.window.conf.update_channel, "dev")
        self.assertEqual(self.window.conf.wine_release_channel, "dev")
        with mock.patch.object(self.window, "start_thread"):
            self.window.s_releases.setChecked(True)
        self.assertEqual(self.window.conf.update_channel, "stable")
        self.assertEqual(self.window.conf.wine_release_channel, "stable")

    def test_settings_tile_shows_formatted_text_not_markup(self):
        self.assertEqual(self.window.t_settings.textFormat(), QtCore.Qt.TextFormat.RichText)

    def test_integrations_installed_by_the_offer_load_straight_away(self):
        installed = iter([False, True])
        with mock.patch.object(gui_main.desktop_integrations, "is_installed", side_effect=lambda: next(installed)), \
                mock.patch.object(gui_main.desktop_integrations, "offer"), \
                mock.patch.object(self.window, "_load_integrations") as load:
            self.window._offer_integrations()
        load.assert_called_once()

    def test_integrations_reload_when_logos_closes(self):
        self.window._last_state = gui_main.State.RUNNING
        with mock.patch.object(self.window, "start_thread") as start, mock.patch.object(self.window, "refresh"):
            self.window._logos_state_changed(gui_main.State.STOPPED)
        start.assert_called_once_with(self.window._load_integrations)

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


if __name__ == "__main__":
    unittest.main()
