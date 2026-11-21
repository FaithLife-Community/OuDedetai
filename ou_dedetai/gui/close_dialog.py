"""Stop: ask Logos to close and wait, showing whether it appears to be syncing."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QProgressBar, QVBoxLayout

from . import style
from .blocks import button, label
from .style import tr

if TYPE_CHECKING:
    from .window import MainWindow


class CloseLogosDialog(QDialog):
    """Stop: ask Logos to close politely and wait, showing whether it appears to be syncing.
    Forcing it is offered, with a warning, but never done without the user."""
    progressed = Signal(bool, float)
    finished_closing = Signal(bool)

    def __init__(self, window: "MainWindow", on_closed: Optional[Callable[[], None]] = None):
        super().__init__(window.root)
        self.main = window
        self.on_closed = on_closed
        self.cancelled = False
        self.setWindowTitle(tr("Closing Logos"))
        self.setWindowIcon(style.app_icon())
        v = QVBoxLayout(self)
        self.text = label(tr("Asking Logos to close…"))
        self.text.setMinimumWidth(380)
        v.addWidget(self.text)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        v.addWidget(self.bar)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.force = button(tr("Force Logos to close…"), "danger", self._force)
        buttons.addWidget(self.force)
        self.hide_btn = button(tr("Stop waiting"), None, self.reject)
        buttons.addWidget(self.hide_btn)
        v.addLayout(buttons)
        self.progressed.connect(self._show_progress)
        self.finished_closing.connect(self._done)
        self.rejected.connect(self._cancel)

    def start(self) -> None:
        self.show()
        self.main.start_thread(self._wait)

    def _wait(self) -> None:
        def progress(busy: bool, idle: float) -> bool:
            self.progressed.emit(busy, idle)
            return self.cancelled
        closed = self.main.logos.close(timeout=float("inf"), progress=progress)
        if not self.cancelled:
            self.finished_closing.emit(closed)

    def _show_progress(self, busy: bool, idle: float) -> None:
        if busy:
            self.text.setText(tr("Logos appears to be syncing or saving. Waiting for it to finish…"))
        elif idle > 10:
            self.text.setText(tr("Logos hasn't closed. It may be asking you something: check its window.\n\n"
                                 "If its window has already gone, Logos is stuck shutting down and forcing "
                                 "it to close is safe."))
        else:
            self.text.setText(tr("Waiting for Logos to close…"))
        self.adjustSize()  # a wrapped label doesn't grow its dialog by itself

    def _force(self) -> None:
        answer = QMessageBox.warning(
            self, tr("Force Logos to close?"),
            tr("Forcing Logos to close stops it at once. Changes that haven't synced to your Faithlife "
               "account yet, or unsaved work, may be lost."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.cancelled = True
        self.main.start_thread(self.main.logos.force_close)
        self._done(True)

    def _cancel(self) -> None:
        self.cancelled = True

    def _done(self, closed: bool) -> None:
        if closed:
            self.cancelled = True
            self.accept()
            if self.on_closed:
                self.on_closed()
