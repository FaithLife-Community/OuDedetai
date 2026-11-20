"""Screenshots of Ou Dedetai's window for the docs, drawn offscreen with stand-in data.

    QT_QPA_PLATFORM=offscreen python scripts/make-screenshots.py docs/images

Nothing is installed and nothing connects to the internet: the window is shown an
installed Logos, a reading plan, saved layouts and applied Wine settings that are all
made up here, so the pictures show no one's real install. Run it from a venv with the
app's requirements (pip install .), ideally with the Inter font installed.
"""
import os
import sys
from pathlib import Path
from unittest import mock

from PySide6 import QtCore, QtGui, QtWidgets

from ou_dedetai import config, constants, desktop_integrations, gui_main, installer, logos, system, wine_settings
from ou_dedetai.cli_parser import get_parser, od_parse_args
from ou_dedetai.logos import State

PLANS = [
    {"title": "Bible in a Year", "kind": "plan", "status": "Day 324 of 365", "progress": 0.89,
     "readings": [{"label": "Ezekiel 40–41", "url": "logosref:Bible.Eze40"},
                  {"label": "Hebrews 9", "url": "logosref:Bible.Heb9"},
                  {"label": "Psalm 119:153–176", "url": "logosref:Bible.Ps119.153"}]},
    {"title": "Daily devotional", "kind": "devotional",
     "readings": [{"label": "The word of God is not bound", "url": "logosres:dev;ref=x"}]},
]
LAYOUTS = ["Sermon prep", "Greek study", "Blank"]
UPDATES = {
    "wine": (True, "Update Wine to wine-custom_11.22_oinos-pre-c3d4e5f"),
    "app": (False, "Ou Dedetai is up to date"),
    "logos": (False, "Logos updates itself"),
    "aks": (False, "Akousousin is up to date"),
    "desktop": (False, "Desktop integrations are up to date"),
}
HEALTH = [
    (True, "Logos is installed", "C:\\users\\you\\AppData\\Local\\Logos\\Logos.exe"),
    (True, "No Wine left running", "Nothing left over"),
    (True, "Wine settings", "All applied"),
    (True, "Graphics (OpenGL)", "OpenGL 4.6 found"),
    (True, "Internet", "Online"),
    (True, "Desktop integrations", "Installed"),
]
INSTALL_STEPS_DONE = (
    "Ensuring installation directories", "Ensuring system dependencies are met", "Ensuring Wine is downloaded",
    "Ensuring winetricks", "Ensuring Logos installer is downloaded", "Ensuring wineprefix is initialized",
    "Ensuring wineprefix configuration",
)


def applied_reports(_app):
    context = wine_settings.SettingsContext(oinos=True)
    return [wine_settings.SettingReport(s, wine_settings.State.APPLIED,
                                        s.needed_with(context) if s.needed_with else True)
            for s in wine_settings.SETTINGS]


class Shots:
    def __init__(self, out: Path):
        self.out = out
        self.installed = True
        out.mkdir(parents=True, exist_ok=True)
        for patch in self._stand_ins():
            patch.start()
        # --offline keeps this script off the network; the window is told it's online.
        ephemeral, _ = od_parse_args(get_parser().parse_args(["--offline", "-f"]), get_parser())
        self.qt = gui_main._qt_app()
        self.qt.setFont(QtGui.QFont("Inter", 10))
        self.w = gui_main.MainWindow(gui_main.Root(), ephemeral)
        self.w.run_health_checks = lambda: None  # the screenshot shows HEALTH instead
        self.w.conf._raw.faithlife_product = "Logos"
        self.w.conf._overrides.offline = False
        self.w._plans, self.w._layouts = PLANS, LAYOUTS
        self.w._render_reading()

    def _stand_ins(self):
        window, conf = gui_main.MainWindow, config.Config
        prop = mock.PropertyMock
        return [
            mock.patch.object(window, "is_installed", lambda _self: self.installed),
            mock.patch.object(window, "_check_updates", lambda _self: {}),
            mock.patch.object(window, "_oinos", lambda _self: True),
            mock.patch.object(window, "_wine_label", lambda _self: "11.22 (oinos)"),
            mock.patch.object(conf, "installed_faithlife_product_release", new_callable=prop,
                              return_value="55.0.0.362"),
            mock.patch.object(conf, "faithlife_product_icon_path", new_callable=prop,
                              return_value=constants.APP_IMAGE_DIR / "Logos-128-icon.png"),
            mock.patch.object(conf, "faithlife_product_logging", new_callable=prop, return_value=True),
            mock.patch.object(wine_settings, "report_for_app", applied_reports),
            mock.patch.object(wine_settings, "renderer_summary", lambda _app: "dxvk"),
            mock.patch.object(gui_main.wine, "get_win_version", lambda _app, _exe: ""),
            mock.patch.object(desktop_integrations, "is_installed", lambda env=None: True),
            mock.patch.object(desktop_integrations, "desktop", lambda env=None: "plasma"),
            mock.patch.object(desktop_integrations, "reading_plans", lambda: PLANS),
            mock.patch.object(desktop_integrations, "saved_layouts", lambda: LAYOUTS),
            mock.patch.object(desktop_integrations, "offer", lambda _app: None),
            mock.patch.object(desktop_integrations, "update_available", lambda _app: None),
            mock.patch.object(system, "akousousin_installed", lambda: True),
            mock.patch.object(system, "akousousin_update", lambda _app: None),
            mock.patch.object(installer, "offer_to_replace_installed", lambda _app: False),
            mock.patch.object(installer, "copy_icons", lambda *_args: None),
            mock.patch.object(logos.LogosManager, "monitor", lambda _self: None),
            mock.patch.object(gui_main.network, "is_offline", lambda: False),
        ]

    def settle(self, rounds: int = 15) -> None:
        for _ in range(rounds):
            self.qt.processEvents()
            QtCore.QThread.msleep(15)

    def save(self, widget: QtWidgets.QWidget, name: str) -> None:
        self.settle()
        widget.grab().save(str(self.out / name))
        print(f"{name}: {widget.width()}×{widget.height()}")

    def show_updates(self, found: bool) -> None:
        self.w._updates = UPDATES if found else {}
        self.w._show_update_button()

    def full_page(self, page: int, name: str, size=(1100, 820)) -> None:
        self.w.open_full(page)
        self.w.root.resize(*size)
        self.settle()
        self.w.clear_status()
        self.save(self.w.root, name)

    def run(self) -> None:
        w = self.w
        w.logos.logos_state = State.STOPPED

        self.installed = False
        w.show_view(gui_main.SIMPLE)
        w.root.show()
        w.refresh()
        w.clear_status()
        self.save(w.root, "simple-install.png")

        self.installed = True
        w.refresh()
        self.show_updates(True)
        w.clear_status()
        self.settle()
        w._fit_simple()
        self.save(w.root, "simple-run.png")

        w._installing = True
        w.guide.set_product("Logos", constants.APP_IMAGE_DIR / "Logos-128-icon.png")
        w.show_view(gui_main.INSTALLING)
        w.root.resize(720, 640)
        for message in INSTALL_STEPS_DONE:
            w.guide.update_status(message)
        w.status_gui.set_status("Applying Ou Dedetai's settings for this Wine build…", None)
        self.save(w.root, "install-guide.png")
        w._installing = False

        w.refresh()
        self.show_updates(True)
        self.full_page(gui_main.HOME, "home.png")
        self.full_page(gui_main.SETTINGS, "settings.png", (1100, 900))
        w.dev_toggle.setChecked(True)
        self.save(w.dev, "developer-options.png")
        w.dev_toggle.setChecked(False)
        w.open_full(gui_main.TROUBLE)
        w._show_health(HEALTH)
        self.full_page(gui_main.TROUBLE, "troubleshooting.png", (1100, 980))

        w.logos.logos_state = State.RUNNING
        w.refresh()
        self.show_updates(True)
        self.full_page(gui_main.HOME, "home-running.png")
        dialog = gui_main.CloseLogosDialog(w)
        dialog.show()
        dialog._show_progress(True, 0)
        self.save(dialog, "stop-busy.png")
        dialog._show_progress(False, 20)
        self.save(dialog, "stop-asking.png")
        dialog.hide()
        tray = gui_main.TrayController.__new__(gui_main.TrayController)
        tray.window = w
        menu = QtWidgets.QMenu()
        gui_main.TrayController._fill(tray, menu)
        menu.popup(QtCore.QPoint(0, 0))
        self.save(menu, "tray-menu.png")


if __name__ == "__main__":
    Shots(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")).run()
    os._exit(0)  # skip Qt's teardown of the half-started background work
