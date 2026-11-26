"""Running Logos from the window."""
import logging
import time
from typing import TYPE_CHECKING, Callable, Optional, cast

import psutil  # type: ignore[import-untyped]
from PySide6.QtWidgets import QApplication, QMenu

from ... import desktop_integrations
from ...logos import State
from ..close_dialog import CloseLogosDialog
from ..style import tr
from ..tray import TrayController, tray_available
from .base import WindowBase

if TYPE_CHECKING:
    from ..window import MainWindow


# Opens the preferred Bible (logosref: always uses it) at its start.
PREFERRED_BIBLE = "logosref:Bible.Ge1.1"
# A saved layout with this name serves as the Run menu's "Blank" (Logos has no
# built-in empty layout that can be opened by name).
BLANK_LAYOUT = "Blank"


class LogosMixin(WindowBase):
    """Running, stopping and watching Logos, and opening links and layouts in it."""

    def add_open_items(self, menu: QMenu) -> None:
        """Bible, today's readings and saved layouts: the Run menu's and the tray's entries.
        Each starts Logos first if it isn't running."""
        bible = menu.addAction(tr("Bible (your preferred Bible)"))
        bible.triggered.connect(lambda _=False: self.open_link(PREFERRED_BIBLE))
        for plan in self._plans[:3]:
            for reading in (plan.get("readings") or [])[:2]:
                if reading.get("url"):
                    a = menu.addAction(tr("Today's reading: {reading}").format(
                        reading=reading.get("label") or plan.get("title", "")))
                    a.triggered.connect(lambda _=False, url=reading["url"]: self.open_link(url))
        layouts = menu.addMenu(tr("Saved layouts"))
        names = [n for n in self._layouts if n.lower() != BLANK_LAYOUT.lower()]
        for name in names:
            layouts.addAction(name).triggered.connect(lambda _=False, n=name: self.open_layout(n))
        if not names:
            empty = layouts.addAction(tr("None found (needs the desktop integrations)")
                                      if not desktop_integrations.is_installed() else tr("None saved yet"))
            empty.setEnabled(False)
        blank = next((n for n in self._layouts if n.lower() == BLANK_LAYOUT.lower()), None)
        b = menu.addAction(tr("Blank (no panels open)") if blank else
                           tr("Blank: save an empty layout named “Blank” in Logos first"))
        b.setEnabled(blank is not None)
        if blank:
            b.triggered.connect(lambda _=False: self.open_layout(blank))

    def _poll_logos(self) -> None:
        """Timer tick. Looking for Logos's processes scans every process on the system, too
        slow for the GUI thread, so it runs on one worker; the state comes back as a signal."""
        if self._polling:
            return
        self._polling = True
        self._poller.submit(self._check_logos)

    def _check_logos(self) -> None:
        try:
            if self.is_installed():
                self.logos.monitor()
            self.signals.logos_state.emit(self.logos.logos_state)
        except (OSError, psutil.Error) as error:
            logging.warning(f"Couldn't check on Logos: {error}")
        finally:
            self._polling = False

    def _logos_state_changed(self, state: State) -> None:
        self.monitor_timer.setInterval(1000 if self.is_installed() else 10000)
        if state != self._last_state:
            if state == State.STOPPED and self._last_state == State.RUNNING:
                # Readings may have been ticked off and layouts saved in Logos.
                self.start_thread(self._load_integrations)
                # Logos may have updated itself: read its version again.
                self.conf._installed_faithlife_product_release = None
            self._last_state = state
            self.refresh()

    def open_in_logos(self, action: Callable[[], object], wait_for_com: bool = False) -> None:
        """Start Logos if needed, then do something in it (open a link or layout)."""
        def run():
            started = self.logos.logos_state not in (State.RUNNING, State.STARTING)
            if started:
                self.signals.tray.emit()
                self.logos.start()
            deadline = time.monotonic() + 240
            while self.logos.logos_state != State.RUNNING and time.monotonic() < deadline:
                time.sleep(1)
                self.logos.monitor()
            if wait_for_com and started:
                time.sleep(10)  # COM answers once Logos has finished opening its window
            action()
        self.start_thread(run)

    def open_link(self, url: Optional[str]) -> None:
        """Open a Logos link (logosref:, logosres:…), starting Logos first if needed."""
        if url:
            self.open_in_logos(lambda: self._send_link(url))

    def _send_link(self, url: str) -> None:
        if desktop_integrations.is_installed() and desktop_integrations.open_url(url):
            return
        self.logos.send_link(url)  # without the integrations, as the link handler does

    def open_layout(self, name: str) -> None:
        self.open_in_logos(lambda: desktop_integrations.open_layout(name), wait_for_com=True)

    def run_logos(self) -> None:
        self.show_tray()
        self.start_thread(self.logos.start)

    def show_tray(self) -> None:
        """Ou Dedetai in the tray while Logos runs, however Logos was started: closing this
        window then leaves it running there, as when Logos is started from its shortcut."""
        if self._tray is not None and self._tray.timer.isActive():
            return
        if not tray_available():
            return  # the window stays a plain window: closing it quits
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setQuitOnLastWindowClosed(False)
            self._tray = TrayController(cast("MainWindow", self), app)

    def stop_logos(self, on_closed: Optional[Callable[[], None]] = None) -> None:
        """Close Logos politely; forcing it is offered, with a warning (CloseLogosDialog)."""
        self._close_dialog = CloseLogosDialog(cast("MainWindow", self), on_closed)
        self._close_dialog.start()
