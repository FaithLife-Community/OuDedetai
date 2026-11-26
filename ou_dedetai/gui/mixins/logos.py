"""Running Logos from the window."""
import logging
import time
from typing import TYPE_CHECKING, Callable, Optional, cast

import psutil  # type: ignore[import-untyped]
from PySide6.QtWidgets import QApplication, QMenu

from ... import desktop_integrations
from ...logos import STARTING_TIMEOUT, State
from ..close_dialog import CloseLogosDialog
from ..style import tr
from ..tray import TrayController
from .base import WindowBase

if TYPE_CHECKING:
    from ..window import MainWindow


# Opens the preferred Bible (logosref: always uses it) at its start.
PREFERRED_BIBLE = "logosref:Bible.Ge1.1"
# A saved layout with this name serves as the Run menu's "Blank" (Logos has no
# built-in empty layout that can be opened by name).
BLANK_LAYOUT = "Blank"
# Logos answers COM only once it has finished opening, some time after its processes
# appear (RUNNING): try the layout for this long, each try cut short after LAYOUT_TRY.
LAYOUT_READY_TIMEOUT = 120
LAYOUT_TRY = 30
LAYOUT_RETRY_PAUSE = 5


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
            with self._logos_checked:
                self._logos_checked.notify_all()  # anything waiting for Logos (_wait_for_logos)

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

    def _start_logos_if_needed(self) -> None:
        """Start Logos unless it's running or starting. Looks afresh first: starting a second
        Logos stops the one that's running (wineserver -k)."""
        self.logos.monitor()
        if self.logos.logos_state not in (State.RUNNING, State.STARTING):
            self.signals.tray.emit()
            self.logos.start()

    def _wait_for_logos(self) -> bool:
        """Wait until Logos runs, or has clearly failed to start. Woken by the window's own
        checks on Logos (_check_logos), so this adds no polling of its own."""
        seen_starting = False

        def settled() -> bool:
            nonlocal seen_starting
            state = self.logos.logos_state
            seen_starting = seen_starting or state == State.STARTING
            return state == State.RUNNING or (seen_starting and state == State.STOPPED)
        with self._logos_checked:
            self._logos_checked.wait_for(settled, timeout=STARTING_TIMEOUT + 30)
        return self.logos.logos_state == State.RUNNING

    def open_link(self, url: Optional[str]) -> None:
        """Open a Logos link (logosref:, logosres:…), starting Logos first if needed."""
        if not url:
            return

        def run():
            self.logos.monitor()  # afresh: starting a second Logos would stop the running one
            state = self.logos.logos_state
            if state == State.STARTING and self._wait_for_logos():
                state = State.RUNNING  # wait until it can take the link (Logos.exe <link>)
            if state == State.RUNNING:
                self._send_link(url)
                return
            # Not running: Logos starts with the link on its command line, as the shortcut
            # does, so nothing has to wait for it.
            self.conf._overrides.logos_link = url
            self.signals.tray.emit()
            self.logos.start()
        self.start_thread(run)

    def _send_link(self, url: str) -> None:
        if desktop_integrations.is_installed() and desktop_integrations.open_url(url):
            return
        self.logos.send_link(url)  # without the integrations, as the link handler does

    def open_layout(self, name: str) -> None:
        """Load a saved layout, starting Logos first if needed. Layouts can only be
        loaded over COM, so Logos has to be up and answering first."""
        def run():
            self._start_logos_if_needed()
            if self._wait_for_logos():
                deadline = time.monotonic() + LAYOUT_READY_TIMEOUT
                while True:
                    if desktop_integrations.open_layout(name, timeout=LAYOUT_TRY):
                        return
                    if time.monotonic() > deadline:
                        break
                    time.sleep(LAYOUT_RETRY_PAUSE)
                message = tr("Logos didn't open the layout “{name}”.")
            else:
                message = tr("Logos didn't start, so the layout “{name}” couldn't be opened.")
            logging.warning(message.format(name=name))
            self.signals.failed.emit(message.format(name=name))
        self.start_thread(run)

    def run_logos(self) -> None:
        self.show_tray()
        self.start_thread(self.logos.start)

    def show_tray(self) -> None:
        """Ou Dedetai in the tray while Logos runs, however Logos was started: closing this
        window then leaves it running there, as when Logos is started from its shortcut."""
        if self._tray is not None and self._tray.timer.isActive():
            return
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setQuitOnLastWindowClosed(False)
            self._tray = TrayController(cast("MainWindow", self), app)

    def stop_logos(self, on_closed: Optional[Callable[[], None]] = None) -> None:
        """Close Logos politely; forcing it is offered, with a warning (CloseLogosDialog)."""
        self._close_dialog = CloseLogosDialog(cast("MainWindow", self), on_closed)
        self._close_dialog.start()
