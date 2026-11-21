"""Ou Dedetai's Qt windows.

Two views of the same window:

- the simple view (the default): Install, or Run / Update / Stop, so it "just works";
- the full view: Home (status, reading plan, integrations), Settings (what Ou Dedetai sets
  in Wine and why, offline mode, developer options) and Troubleshooting.

While installing, the window shows a guide: each step in plain words.

When Logos is started from its shortcut and there's a display, Ou Dedetai sits in the
system tray while Logos runs (`TrayController`). Every tray item is also in the window,
because not every desktop shows a tray.

All operations are the existing UI-agnostic ones (installer, logos, wine, control…);
the window only arranges them. This module holds the window's frame: its views, pages and
refresh. Each feature is a mixin in gui/mixins (see mixins/base.py).
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMessageBox, QSizePolicy, QStackedWidget, QVBoxLayout,
    QWidget,
)

from ou_dedetai.config import EphemeralConfiguration

from .. import constants, installer, network
from ..logos import State
from . import style, widgets
from .app import GuiApp, Root
from .blocks import FULL, HOME, SETTINGS, SIMPLE, TROUBLE, button, label, product_name, scrolled
from .close_dialog import CloseLogosDialog
from .install_guide import InstallGuide
from .mixins.akousousin import AkousousinMixin
from .mixins.home import HomePageMixin
from .mixins.install import InstallMixin
from .mixins.integrations import IntegrationsMixin
from .mixins.logos import LogosMixin
from .mixins.settings import SettingsMixin
from .mixins.simple import SimpleViewMixin
from .mixins.troubleshoot import TroubleshootMixin
from .mixins.updates import UpdatesMixin
from .mixins.wine_builds import WineBuildsMixin
from .style import tr
from .tray import TrayController


class Signals(QObject):
    """What background work reports back. Emitted from worker threads; Qt queues each
    emission onto the GUI thread, where the connected MainWindow slot runs."""
    status = Signal(str, object)         # message, percent or None
    refresh = Signal()                   # config or state changed: redraw
    settings_changed = Signal()          # a Wine setting changed: redraw Settings too
    logos_state = Signal(object)         # ou_dedetai.logos.State
    integrations = Signal(list, list)    # reading plans, saved layouts
    updates = Signal(dict)               # what can be updated
    health = Signal(list)                # (ok, title, detail) results
    recheck = Signal()                   # run the health checks again
    winver = Signal(str, str)            # Windows version for Logos, indexer
    install_finished = Signal()
    failed = Signal(str)                 # an unexpected error in a background task
    task_done = Signal()                 # a background task returned
    tray = Signal()                      # Logos is being started: show the tray
    wine_builds = Signal(dict)           # channel → newest Wine bundle's name


class MainWindow(
    SimpleViewMixin, HomePageMixin, SettingsMixin, TroubleshootMixin, InstallMixin, LogosMixin, UpdatesMixin,
    WineBuildsMixin, IntegrationsMixin, AkousousinMixin, GuiApp,
):
    """The GUI front end: simple view, install guide and full view."""

    def __init__(self, root: Root, ephemeral_config: EphemeralConfiguration, show: bool = True):
        self.status_gui = widgets.StatusGui()
        super().__init__(root, self.status_gui, ephemeral_config)
        self.root.setWindowTitle(constants.APP_NAME)
        self.root.setWindowIcon(style.app_icon())
        self._plans: list[dict] = []
        self._layouts: list[str] = []
        self.while_closed: list[QWidget] = []
        self._updates: dict[str, tuple[bool, str]] = {}
        self._tray: Optional["TrayController"] = None
        self._close_dialog: Optional["CloseLogosDialog"] = None
        self._wine_builds_known = False
        self._installing = False
        self._last_state: Optional[State] = None
        self._polling = False
        self._poller = ThreadPoolExecutor(max_workers=1, thread_name_prefix="logos-monitor")
        self.signals = Signals()

        central = QWidget()
        central.setObjectName("od-root")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.status_gui.setObjectName("od-root")
        status_layout = self.status_gui.layout()
        if status_layout is not None:
            status_layout.setContentsMargins(16, 4, 16, 8)
        outer.addWidget(self.status_gui)
        self.root.set_content(central)

        self.stack.addWidget(self._build_simple())
        self.guide = InstallGuide()
        self.stack.addWidget(self.guide)
        self.stack.addWidget(self._build_full())

        sig = self.signals
        sig.status.connect(self._show_status)
        sig.refresh.connect(self.refresh)
        sig.settings_changed.connect(self._after_change)
        sig.logos_state.connect(self._logos_state_changed)
        sig.integrations.connect(self._integrations_loaded)
        sig.updates.connect(self._updates_checked)
        sig.health.connect(self._show_health)
        sig.recheck.connect(self.run_health_checks)
        sig.winver.connect(self._show_winver)
        sig.install_finished.connect(self._install_finished)
        sig.failed.connect(self._task_failed)
        sig.task_done.connect(self._task_done)
        sig.tray.connect(self.show_tray)
        sig.wine_builds.connect(self._show_wine_builds)

        self.config_updated_hooks.append(self._refresh_later)
        self.refresh()
        # Check on Logos every second (every 10 s until it's installed).
        self.monitor_timer = QTimer(self.root)
        self.monitor_timer.timeout.connect(self._poll_logos)
        self.monitor_timer.start(1000)
        self._poll_logos()
        self.start_thread(self._load_integrations)
        self.start_thread(self._check_updates)
        raw = self.conf._raw
        if raw.install_dir and raw.faithlife_product and Path(raw.install_dir).is_dir():
            # Shortcuts made by an older release may still point at an old icon.
            self.start_thread(installer.copy_icons, raw.install_dir, raw.faithlife_product)
            # A newer Ou Dedetai (e.g. a downloaded test build) run from elsewhere: offer to install it.
            self.start_thread(installer.offer_to_replace_installed, self)
        self.start_thread(self._offer_integrations)
        self.show_view(FULL if self.conf.gui_full_view and self.is_installed() else SIMPLE)
        if show:
            self.root.show()

    def _status(self, message, percent=None):
        self.signals.status.emit(message, percent)

    def clear_status(self):
        self.signals.status.emit("", 0)

    def start_thread(self, task, *args, daemon_bool: bool = True, **kwargs):
        """Run a task in the background. An error nothing else handled is logged and shown
        to the user instead of vanishing with the thread."""
        def guarded():
            try:
                task(*args, **kwargs)
            except Exception as error:  # top of the thread: nothing above us to handle it
                logging.exception(f"Background task {name} failed")
                self.signals.failed.emit(str(error) or type(error).__name__)
            finally:
                self.signals.task_done.emit()
        name = getattr(task, "__name__", str(task))
        guarded.__name__ = name
        return super().start_thread(guarded, daemon_bool=daemon_bool)

    def _show_status(self, message: str, percent: Optional[int]) -> None:
        self.status_gui.set_status(message, percent)
        if self._installing:
            self.guide.update_status(message)
            if message.startswith("Install Complete"):
                self._install_finished()

    def _task_done(self) -> None:
        # A task that ended on a message without a percentage would leave the bar
        # animating forever; keep the message, stop the animation.
        bar = self.status_gui.progress
        if bar.maximum() == 0 and not self._installing:
            bar.setRange(0, 100)
            bar.setVisible(False)

    def _task_failed(self, error: str) -> None:
        self.status_gui.set_status(tr("Something went wrong: {error}").format(error=error), None)
        QMessageBox.warning(
            self.root, tr("Something went wrong"),
            tr("{error}\n\nThe log has the details; Troubleshooting → Save a support report collects it.").format(
                error=error))

    def show_view(self, view: int) -> None:
        # Only the visible page counts towards the window's minimum size; otherwise the
        # full view's size would stop the simple window shrinking back.
        policy = QSizePolicy.Policy
        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            if page is not None:
                page.setSizePolicy(*(2 * (policy.Preferred if i == view else policy.Ignored,)))
        self.stack.setCurrentIndex(view)
        self.stack.updateGeometry()
        if view == FULL:
            self._fit_full()
        elif view == SIMPLE:
            self._fit_simple()

    def _fit_full(self) -> None:
        """At least big enough for the full view's content, within the screen."""
        page = self.stack.widget(FULL)
        hint = page.sizeHint() if page is not None else QSize(0, 0)
        width = max(self.root.width(), 1040, hint.width())
        height = max(self.root.height(), 700, hint.height())
        screen = self.root.screen()
        if screen is not None:
            available = screen.availableGeometry()
            width, height = min(width, available.width()), min(height, available.height())
        self.root.resize(width, height)

    def _fit_simple(self) -> None:
        """Size the window to the simple view's content (no empty band)."""
        page = self.stack.widget(SIMPLE)
        if page is None or self.stack.currentIndex() != SIMPLE:
            # A fit queued by refresh() before the full view opened (e.g. at start-up
            # with the full view as default) would shrink it to the simple size.
            return
        width = 720
        # Measure without resizing the page itself (adjustSize() here left the page
        # narrower than the window until the next resize).
        layout = page.layout()
        if layout is not None and layout.hasHeightForWidth():
            height = layout.heightForWidth(width)
        else:
            height = page.sizeHint().height()
        if not self.status_gui.isHidden():
            height += self.status_gui.sizeHint().height()
        self.root.resize(width, max(height, 260))

    def _build_full(self) -> QWidget:
        page = QWidget()
        page.setObjectName("od-page")
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(260)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 16, 12, 16)
        sv.setSpacing(2)
        brand = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(style.pixmap(constants.APP_IMAGE_DIR / "icon.png", 36))
        brand.addWidget(icon)
        names = QVBoxLayout()
        n = label(constants.APP_NAME, "brand")
        names.addWidget(n)
        names.addWidget(label(tr("Logos on Linux"), "muted"))
        brand.addLayout(names, 1)
        sv.addLayout(brand)
        sv.addSpacing(12)
        self.nav = QButtonGroup(side)
        for i, text in enumerate((tr("Home"), tr("Settings"), tr("Troubleshooting"))):
            b = button(text, "nav")
            b.setCheckable(True)
            self.nav.addButton(b, i)
            sv.addWidget(b)
        self.nav.idClicked.connect(self.show_page)
        sv.addSpacing(8)
        sv.addWidget(button(tr("Simple view"), "link", lambda: self.show_view(SIMPLE)))
        sv.addStretch(1)
        self.reading_card = self._build_reading_card()
        sv.addWidget(self.reading_card)
        h.addWidget(side)

        self.pages = QStackedWidget()
        self.pages.addWidget(scrolled(self._build_home()))
        self.pages.addWidget(scrolled(self._build_settings()))
        self.pages.addWidget(scrolled(self._build_trouble()))
        h.addWidget(self.pages, 1)
        self.show_page(HOME)
        return page

    def show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        button_ = self.nav.button(index)
        if button_:
            button_.setChecked(True)
        if index == SETTINGS:
            self.refresh_settings()
        elif index == TROUBLE:
            self.run_health_checks()

    def open_full(self, page: int = HOME) -> None:
        self.show_view(FULL)
        self.show_page(page)

    def closed_only(self, widget):
        """Grey `widget` out while Logos is open (see `while_closed`)."""
        self.while_closed.append(widget)
        return widget

    def _logos_open(self) -> bool:
        return self.logos.logos_state in (State.RUNNING, State.STARTING)

    def _refresh_later(self, *_):
        self.signals.refresh.emit()

    def refresh(self) -> None:
        self._refresh()
        if self.stack.currentIndex() == SIMPLE:
            QTimer.singleShot(0, self._fit_simple)

    def _refresh(self) -> None:
        product = self.conf._raw.faithlife_product or constants.FAITHLIFE_PRODUCTS[0]
        installed = self.is_installed()
        icon = self.conf.faithlife_product_icon_path if self.conf._raw.faithlife_product else \
            constants.APP_IMAGE_DIR / "Logos-128-icon.png"
        running = self.logos.logos_state in (State.RUNNING, State.STARTING)
        for b in self.s_products.buttons():
            b.blockSignals(True)
            b.setChecked(b.text() == product)
            b.blockSignals(False)
        if installed:
            title = product_name(product)
            state = tr("Running") if self.logos.logos_state == State.RUNNING else (
                tr("Starting…") if self.logos.logos_state == State.STARTING else tr("Ready"))
            version = self.conf.installed_faithlife_product_release or ""
            state_line = f"{state} · {tr('version {version}').format(version=version)}" if version else state
        else:
            title = tr("Install {product}").format(product=product_name(product))
            state_line = tr("Not installed yet")
        self.s_icon.setPixmap(style.pixmap(icon, 64))
        self.h_icon.setPixmap(style.pixmap(icon, 56))
        self.s_title.setText(title)
        self.h_title.setText(title)
        self.s_state.setText(state_line)
        self.h_state.setText(state_line)
        self.s_install_box.setVisible(not installed)
        self.s_run_box.setVisible(installed)
        self.s_hint.setVisible(installed)
        self.s_full_default.blockSignals(True)
        self.s_full_default.setChecked(self.conf.gui_full_view)
        self.s_full_default.blockSignals(False)
        offline = network.is_offline()
        self.s_install.setEnabled(not offline and not self._installing)
        self.s_needs.setText(tr("Offline mode is on: installing needs a connection.") if offline else
                             tr("Needs an internet connection."))
        for b in (self.s_run, self.h_run):
            b.setText(tr("Run {product}").format(product=product))
            b.setEnabled(installed and not running)
        self.s_stop.setEnabled(running)
        self.h_stop.setEnabled(running)
        self.h_stop.setVisible(installed)
        for widget in self.while_closed:
            widget.setEnabled(installed and not running)
            widget.setToolTip(tr("Close Logos first") if running else "")
        self.h_run.setVisible(installed)
        self.h_install.setVisible(not installed)
        self.h_install.setEnabled(not offline and not self._installing)
        self.s_options.setEnabled(not offline and not self._installing)
        self.s_update.setEnabled(installed)
        self.h_update.setEnabled(installed)
        self.h_update.setVisible(installed)
        self._show_update_button()
        self._refresh_home(installed, offline)
        self._refresh_switches()
        self._show_akousousin()
        self._show_desktop_integrations()
        self._refresh_trouble()


def _qt_app() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else \
        QApplication([constants.BINARY_NAME])
    app.setApplicationName(constants.APP_NAME)
    app.setDesktopFileName(constants.BINARY_NAME)
    style.apply(app)
    return app


def start(ephemeral_config: EphemeralConfiguration, install: bool = False) -> int:
    """The window (control panel). With `install`, start installing straight away."""
    app = _qt_app()
    root = Root()
    window = MainWindow(root, ephemeral_config)
    if install and not window.is_installed():
        window.run_install()
    return app.exec()


def run_with_tray(ephemeral_config: EphemeralConfiguration) -> int:
    """Start Logos and keep Ou Dedetai in the tray while it runs (the Logos shortcut)."""
    app = _qt_app()
    app.setQuitOnLastWindowClosed(False)
    root = Root()
    window = MainWindow(root, ephemeral_config, show=False)
    if not window.is_installed():
        window.root.show()
        return app.exec()
    if window.logos.hand_off_link():
        return 0  # a link for the Logos that's already running: nothing more to do
    window.start_thread(window.logos.start)
    window._tray = TrayController(window, app)
    return app.exec()


def display_available() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
