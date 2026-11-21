"""Ou Dedetai in the system tray while Logos runs from its shortcut."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .. import constants
from ..logos import State
from . import style
from .blocks import FULL, HOME, SIMPLE, TROUBLE
from .style import tr

if TYPE_CHECKING:
    from .window import MainWindow


class TrayController(QObject):
    """Ou Dedetai in the system tray while Logos runs; leaves when Logos closes."""

    def __init__(self, window: MainWindow, qt_app: QApplication):
        super().__init__()
        self.window = window
        self.qt_app = qt_app
        self.seen_running = False
        self.tray: Optional[QSystemTrayIcon] = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(style.app_icon())
            self.tray.setToolTip(constants.APP_NAME)
            menu = QMenu()
            menu.aboutToShow.connect(lambda: self._fill(menu))
            self._fill(menu)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._activated)
            self.tray.show()
        else:
            logging.info("No system tray on this desktop: Ou Dedetai runs in the background without an icon.")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(3000)

    def _fill(self, menu: QMenu) -> None:
        menu.clear()
        state = self.window.logos.logos_state
        head = menu.addAction(tr("Logos is running") if state == State.RUNNING else tr("Logos is starting…"))
        head.setEnabled(False)
        w = self.window
        w.add_open_items(menu)
        stop = menu.addAction(tr("Stop Logos"))
        stop.triggered.connect(lambda: w.stop_logos())
        menu.addSeparator()
        show = menu.addAction(tr("Ou Dedetai…"))
        show.triggered.connect(lambda: self.show_window(SIMPLE))
        trouble = menu.addAction(tr("Troubleshooting…"))
        trouble.triggered.connect(lambda: self.show_window(FULL, TROUBLE))
        menu.addSeparator()
        menu.addAction(tr("Quit Ou Dedetai")).triggered.connect(self.quit)

    def quit(self) -> None:
        """Leave the tray. While Logos runs, warn first: Ou Dedetai is what notices Logos
        closing and tidies up after it."""
        state = self.window.logos.logos_state
        if state in (State.RUNNING, State.STARTING):
            box = QMessageBox(QMessageBox.Icon.Warning, constants.APP_NAME,
                                        tr("Logos is still running."))
            box.setInformativeText(tr(
                "Ou Dedetai looks after Logos while it runs and tidies up when Logos closes. "
                "Without it, Logos keeps running with no tray icon to stop it. It's safest to close Logos first."))
            stop = box.addButton(tr("Close Logos and quit"), QMessageBox.ButtonRole.AcceptRole)
            leave = box.addButton(tr("Quit anyway"), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(stop)
            box.exec()
            if box.clickedButton() is stop:
                # Politely, as its close button does, so Logos can finish syncing and ask about
                # unsaved work; the dialog offers forcing it, with a warning.
                self.window.stop_logos(on_closed=self._leave)
                return
            if box.clickedButton() is not leave:
                return
        self._leave()

    def _leave(self) -> None:
        self.timer.stop()
        if self.tray:
            self.tray.hide()
        self.qt_app.quit()

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window(SIMPLE)

    def show_window(self, view: int, page: int = HOME) -> None:
        if view == FULL:
            self.window.open_full(page)
        else:
            self.window.show_view(view)
        self.window.root.show()
        self.window.root.raise_()
        self.window.root.activateWindow()

    def _tick(self) -> None:
        state = self.window.logos.logos_state
        if state == State.RUNNING:
            self.seen_running = True
        elif state == State.STOPPED and self.seen_running:
            # Logos has closed: leave the tray, and quit unless the window is open.
            if self.tray:
                self.tray.hide()
            if not self.window.root.isVisible():
                self.qt_app.quit()
            else:
                self.qt_app.setQuitOnLastWindowClosed(True)
                self.timer.stop()
