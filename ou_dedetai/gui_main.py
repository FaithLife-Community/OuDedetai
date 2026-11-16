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
this module only arranges them.
"""
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

import ou_dedetai.logos
from ou_dedetai.config import EphemeralConfiguration

from . import (
    backup, constants, control, desktop_integrations, gui, gui_style, installer, network,
    system, utils, wine, wine_settings,
)
from .gui_app import GuiApp, InstallerWindow, Root, Toplevel

State = ou_dedetai.logos.State
CONTEXT = "OuDedetai"


def tr(text: str) -> str:
    """Translate a GUI string (Qt Linguist files in ou_dedetai/i18n)."""
    return QtCore.QCoreApplication.translate(CONTEXT, text)


# ── Small building blocks ────────────────────────────────────────────────────

def label(text: str = "", role: Optional[str] = None, wrap: bool = True) -> QtWidgets.QLabel:
    w = QtWidgets.QLabel(text)
    w.setWordWrap(wrap)
    w.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    if role:
        w.setProperty("role", role)
    return w


def pill(text: str, kind: str) -> QtWidgets.QLabel:
    w = QtWidgets.QLabel(text)
    w.setProperty("pill", kind)
    w.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
    return w


def set_pill(w: QtWidgets.QLabel, text: str, kind: str) -> None:
    w.setText(text)
    w.setProperty("pill", kind)
    w.style().unpolish(w)
    w.style().polish(w)


def button(text: str, kind: Optional[str] = None, slot: Optional[Callable] = None) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(lambda _=False: slot())
    b.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    return b


def card(accent: Optional[str] = None) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    frame = QtWidgets.QFrame()
    frame.setObjectName("card")
    if accent:
        frame.setProperty("accent", accent)
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(8)
    return frame, layout


def row(title: str, subtitle: str = "", right: Optional[QtWidgets.QWidget] = None,
        left: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget:
    """A card row: optional left widget, bold title + muted subtitle, optional right widget."""
    w = QtWidgets.QFrame()
    w.setObjectName("rowline")
    h = QtWidgets.QHBoxLayout(w)
    h.setContentsMargins(0, 8, 0, 4)
    h.setSpacing(12)
    if left is not None:
        h.addWidget(left, 0, QtCore.Qt.AlignmentFlag.AlignTop)
    text = QtWidgets.QVBoxLayout()
    text.setSpacing(1)
    t = label(title)
    t.setStyleSheet("font-weight: 600;")
    text.addWidget(t)
    if subtitle:
        text.addWidget(label(subtitle, "muted"))
    h.addLayout(text, 1)
    if right is not None:
        h.addWidget(right, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    return w


def scrolled(widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    area = QtWidgets.QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    widget.setObjectName("od-page")
    area.setWidget(widget)
    return area


def leftover_wine(prefix: Optional[str]) -> list[int]:
    """PIDs of Wine processes still running in this prefix."""
    import psutil  # type: ignore[import-untyped]
    if not prefix:
        return []
    want = str(Path(prefix).resolve())
    pids = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = (process.info["name"] or "").lower()
            if not (name.startswith("wine") or name.endswith(".exe")):
                continue
            env_prefix = process.environ().get("WINEPREFIX")
            if env_prefix and str(Path(env_prefix).resolve()) == want:
                pids.append(process.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            pass
    return pids


def clear_layout(layout: QtWidgets.QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widget.deleteLater()


def renderer_name(value: str) -> str:
    return {"dxvk": "DXVK", "gl": "OpenGL", "vulkan": "Vulkan", "gdi": "GDI",
            "default": tr("Wine default"), "unknown": tr("Unknown")}.get(value, value)


def open_path(path: str | Path) -> None:
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))


# ── The install guide ────────────────────────────────────────────────────────

# Status messages from installer.py, in order, matched by their start, with plain words.
INSTALL_STEPS: list[tuple[tuple[str, ...], str, str]] = [
    (("Asking questions", "Install is running", "Ensuring installation directories"),
     "Preparing", "Choosing where Logos goes"),
    (("Ensuring system dependencies", "Checking available OpenGL"),
     "Checking your computer", "Graphics and the system packages Wine needs"),
    (("Ensuring Wine is downloaded", "Ensuring wine executables", "Creating wine symlinks"),
     "Getting Wine", "Wine runs Windows programs. It's kept in Ou Dedetai's folder, not system-wide"),
    (("Ensuring winetricks",),
     "Getting winetricks", "A helper used to add one Windows font"),
    (("Ensuring Logos installer", "Ensuring Verbum installer"),
     "Downloading the installer", "From Faithlife"),
    (("Ensuring wineprefix is initialized",),
     "Creating a Windows folder for Logos", "Called a Wine prefix"),
    (("Ensuring wineprefix configuration", "Configuring font", "Ensuring Akousousin"),
     "Applying settings Logos needs", ""),
    (("Ensuring ICU", "Copying ICU", "ICU files"),
     "Adding language data (ICU)", "Avoids a crash when Logos lists languages"),
    (("Ensuring Logos is installed", "Ensuring Verbum is installed", "Running MSI installer"),
     "Installing Logos", "Faithlife's own installer runs now"),
    (("Ensuring config file", "Copying launcher", "Creating launcher shortcuts", "Install has finished"),
     "Adding shortcuts and sign-in links", "So Logos is in your app menu and sign-in returns to it"),
]


class InstallGuide(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("od-page")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(32, 22, 32, 22)
        v.setSpacing(12)
        head = QtWidgets.QHBoxLayout()
        self.icon = QtWidgets.QLabel()
        head.addWidget(self.icon)
        titles = QtWidgets.QVBoxLayout()
        self.title = label(tr("Installing Logos"), "title")
        self.subtitle = label(tr("You can use your computer meanwhile."), "muted")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        v.addLayout(head)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName(tr("Install progress"))
        v.addWidget(self.progress)

        frame, steps = card()
        steps.addWidget(label(tr("What's happening"), "h2"))
        self.rows: list[tuple[QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel]] = []
        self.row_widgets: list[QtWidgets.QWidget] = []
        for i, (_, title, detail) in enumerate(INSTALL_STEPS):
            mark = pill(str(i + 1), "off")
            mark.setMinimumWidth(26)
            mark.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(w)
            h.setContentsMargins(0, 4, 0, 4)
            h.addWidget(mark, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            col = QtWidgets.QVBoxLayout()
            col.setSpacing(1)
            t = label(tr(title))
            t.setStyleSheet("font-weight: 600;")
            d = label(tr(detail) if detail else "", "muted")
            d.setVisible(bool(detail))
            col.addWidget(t)
            col.addWidget(d)
            h.addLayout(col, 1)
            steps.addWidget(w)
            self.rows.append((mark, t, d))
            self.row_widgets.append(w)
        # The settings step lists what it sets (the same list Settings shows).
        settings_detail = self.rows[6][2]
        settings_detail.setText(", ".join(
            tr(s.title) for s in wine_settings.SETTINGS if s.group == wine_settings.Group.NEEDED))
        settings_detail.setVisible(True)
        self.area = scrolled_frame(frame)
        v.addWidget(self.area, 1)

        self.detail = label("", "muted")
        v.addWidget(self.detail)
        self.current = -1

    def set_product(self, product: str, icon_path) -> None:
        self.title.setText(tr("Installing {product}").format(product=product))
        self.icon.setPixmap(gui_style.pixmap(icon_path, 44))

    def update_status(self, message: str, percent: Optional[int]) -> None:
        if percent is not None:
            self.progress.setValue(int(percent))
        self.detail.setText(message.strip())
        for i, (prefixes, _, _) in enumerate(INSTALL_STEPS):
            if any(message.startswith(p) for p in prefixes):
                if i >= self.current:
                    self.current = i
                break
        for i, (mark, title, _) in enumerate(self.rows):
            if i < self.current or (message.startswith("Install Complete")):
                set_pill(mark, "✓", "ok")
                mark.setAccessibleName(tr("Done"))
            elif i == self.current:
                set_pill(mark, str(i + 1), "warn")
                mark.setAccessibleName(tr("In progress"))
            else:
                set_pill(mark, str(i + 1), "off")
                mark.setAccessibleName(tr("Not started"))
        if 0 <= self.current < len(self.row_widgets):
            self.area.ensureWidgetVisible(self.row_widgets[self.current], 0, 40)


def scrolled_frame(frame: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    area = QtWidgets.QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    area.setWidget(frame)
    return area


# ── The window ───────────────────────────────────────────────────────────────

SIMPLE, INSTALLING, FULL = 0, 1, 2
HOME, SETTINGS, TROUBLE = 0, 1, 2


class MainWindow(GuiApp):
    """The GUI front end: simple view, install guide and full view."""

    def __init__(self, root: Root, ephemeral_config: EphemeralConfiguration, show: bool = True):
        self.status_gui = gui.StatusGui()
        super().__init__(root, self.status_gui, ephemeral_config)
        self.root.setWindowTitle(constants.APP_NAME)
        self.root.setWindowIcon(gui_style.app_icon())
        self._plans: list[dict] = []
        self._layouts: list[str] = []
        self._updates: dict[str, tuple[bool, str]] = {}
        self._installing = False

        central = QtWidgets.QWidget()
        central.setObjectName("od-root")
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QtWidgets.QStackedWidget()
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

        self.config_updated_hooks.append(self._refresh_later)
        self.refresh()
        self.start_thread(self._monitor)
        self.start_thread(self._load_integrations)
        self.start_thread(self._check_updates)
        self.start_thread(desktop_integrations.offer, app=self)
        self.show_view(FULL if self.conf.gui_full_view and self.is_installed() else SIMPLE)
        if show:
            self.root.show()

    # ── App interface ──
    def _status(self, message, percent=None):
        def update():
            self.status_gui.set_status(message, percent)
            if self._installing:
                self.guide.update_status(message, percent)
        self._dispatch(update, wait=False)

    def clear_status(self):
        self._dispatch(lambda: self.status_gui.set_status("", 0), wait=False)

    # ── Views ──
    def show_view(self, view: int) -> None:
        self.stack.setCurrentIndex(view)
        # The install guide has its own progress bar and status line.
        self.status_gui.setVisible(view != INSTALLING)
        if view == FULL:
            self.root.resize(max(self.root.width(), 1040), max(self.root.height(), 700))
        elif view == SIMPLE:
            self.root.resize(720, 480)

    def _build_simple(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        page.setObjectName("od-page")
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(40, 28, 40, 16)
        v.setSpacing(18)

        head = QtWidgets.QHBoxLayout()
        self.s_icon = QtWidgets.QLabel()
        head.addWidget(self.s_icon)
        titles = QtWidgets.QVBoxLayout()
        self.s_title = label("", "title")
        self.s_state = label("", "muted")
        titles.addWidget(self.s_title)
        titles.addWidget(self.s_state)
        head.addLayout(titles, 1)
        v.addLayout(head)

        # Not installed: one Install button.
        self.s_install_box = QtWidgets.QWidget()
        ib = QtWidgets.QVBoxLayout(self.s_install_box)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.setSpacing(12)
        ib.addWidget(label(tr("Ou Dedetai sets up Wine and installs Logos for you. "
                              "You'll sign in to your Faithlife account at the end."), "muted"))
        products = QtWidgets.QHBoxLayout()
        self.s_products = QtWidgets.QButtonGroup(page)
        for name in constants.FAITHLIFE_PRODUCTS:
            r = QtWidgets.QRadioButton(name)
            r.toggled.connect(lambda on, n=name: self._set_product(n) if on else None)
            self.s_products.addButton(r)
            products.addWidget(r)
        products.addStretch(1)
        ib.addLayout(products)
        self.s_install = button(tr("Install"), "primary", self.run_install)
        self.s_install.setMinimumHeight(44)
        ib.addWidget(self.s_install)
        opts = QtWidgets.QHBoxLayout()
        self.s_needs = label("", "muted")
        opts.addWidget(self.s_needs, 1)
        self.s_options = button(tr("Choose options…"), "link", self.run_installer)
        opts.addWidget(self.s_options)
        ib.addLayout(opts)
        v.addWidget(self.s_install_box)

        # Installed: Run ▾ / Update ▾ / Stop.
        self.s_run_box = QtWidgets.QWidget()
        rb = QtWidgets.QHBoxLayout(self.s_run_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(12)
        self.s_run = self._run_button()
        rb.addWidget(self.s_run)
        self.s_update = QtWidgets.QToolButton()
        self.s_update.setText(tr("Update"))
        self.s_update.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.s_update.setMenu(self._update_menu())
        rb.addWidget(self.s_update)
        self.s_stop = button(tr("Stop"), None, self.stop_logos)
        rb.addWidget(self.s_stop)
        rb.addStretch(1)
        v.addWidget(self.s_run_box)

        self.s_hint = label(tr("The arrow next to Run starts Logos with today's reading, a passage or a "
                               "saved layout. While Logos runs, Ou Dedetai sits in the system tray."), "muted")
        v.addWidget(self.s_hint)
        self.s_full_default = QtWidgets.QCheckBox(
            tr("Open the full view when Ou Dedetai starts (reading plan, layouts, status)"))
        self.s_full_default.toggled.connect(lambda on: setattr(self.conf, "gui_full_view", on))
        v.addWidget(self.s_full_default)
        v.addStretch(1)
        foot = QtWidgets.QHBoxLayout()
        foot.addWidget(button(tr("Settings and troubleshooting…"), "link", lambda: self.open_full(SETTINGS)))
        foot.addStretch(1)
        foot.addWidget(label(tr("Ou Dedetai {version} · community supported").format(
            version=constants.LLI_CURRENT_VERSION), "muted", wrap=False))
        v.addLayout(foot)
        return page

    def _run_button(self) -> QtWidgets.QToolButton:
        b = QtWidgets.QToolButton()
        b.setProperty("kind", "primary")
        b.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        b.setMinimumHeight(40)
        b.clicked.connect(self.run_logos)
        menu = QtWidgets.QMenu(b)
        menu.aboutToShow.connect(lambda m=menu: self._fill_run_menu(m))
        b.setMenu(menu)
        b.setAccessibleName(tr("Run Logos"))
        b.setAccessibleDescription(tr("The arrow offers more ways to start Logos"))
        return b

    def _build_full(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        page.setObjectName("od-page")
        h = QtWidgets.QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QtWidgets.QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(260)
        sv = QtWidgets.QVBoxLayout(side)
        sv.setContentsMargins(12, 16, 12, 16)
        sv.setSpacing(2)
        brand = QtWidgets.QHBoxLayout()
        icon = QtWidgets.QLabel()
        icon.setPixmap(gui_style.pixmap(constants.APP_IMAGE_DIR / "icon.png", 36))
        brand.addWidget(icon)
        names = QtWidgets.QVBoxLayout()
        n = label(constants.APP_NAME)
        n.setStyleSheet("font-weight: 700; font-size: 13pt;")
        names.addWidget(n)
        names.addWidget(label(tr("Logos on Linux"), "muted"))
        brand.addLayout(names, 1)
        sv.addLayout(brand)
        sv.addSpacing(12)
        self.nav = QtWidgets.QButtonGroup(side)
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

        self.pages = QtWidgets.QStackedWidget()
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

    def _build_reading_card(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("reading")
        v = QtWidgets.QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QtWidgets.QFrame()
        head.setObjectName("readinghead")
        hv = QtWidgets.QVBoxLayout(head)
        hv.setContentsMargins(12, 8, 12, 8)
        t = label(tr("Today's reading"))
        t.setStyleSheet("font-weight: 600;")
        hv.addWidget(t)
        self.reading_plan = label("", "muted")
        hv.addWidget(self.reading_plan)
        v.addWidget(head)
        body = QtWidgets.QWidget()
        self.reading_body = QtWidgets.QVBoxLayout(body)
        self.reading_body.setContentsMargins(12, 8, 12, 10)
        self.reading_body.setSpacing(4)
        v.addWidget(body)
        frame.setVisible(False)
        return frame

    def _build_home(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)
        hero, hl = card(accent="true")
        top = QtWidgets.QHBoxLayout()
        self.h_icon = QtWidgets.QLabel()
        top.addWidget(self.h_icon)
        col = QtWidgets.QVBoxLayout()
        self.h_title = label("", "title")
        self.h_state = label("", "muted")
        col.addWidget(self.h_title)
        col.addWidget(self.h_state)
        top.addLayout(col, 1)
        self.h_index = button(tr("Run indexing"), None, self.run_indexing)
        top.addWidget(self.h_index)
        self.h_run = self._run_button()
        top.addWidget(self.h_run)
        self.h_install = button(tr("Install"), "primary", self._install_from_full)
        self.h_install.setMinimumHeight(40)
        top.addWidget(self.h_install)
        hl.addLayout(top)
        v.addWidget(hero)

        tiles = QtWidgets.QGridLayout()
        tiles.setSpacing(12)
        self.t_updates = self._tile(tiles, 0, tr("Logos updates"))
        self.t_wine = self._tile(tiles, 1, tr("Wine"))
        self.t_settings = self._tile(tiles, 2, tr("Settings"))
        v.addLayout(tiles)

        both = QtWidgets.QHBoxLayout()
        both.setSpacing(12)
        look, ll = card()
        ll.addWidget(label(tr("Looking after Logos"), "h2"))
        self.p_links = pill("", "ok")
        self.p_graphics = pill("", "ok")
        self.p_tidy = pill(tr("On"), "ok")
        self.p_net = pill("", "off")
        ll.addWidget(row(tr("Sign-in and Bible links"), tr("Sent to Logos by Ou Dedetai's link handler"),
                         self.p_links))
        ll.addWidget(row(tr("Graphics"), tr("Chosen automatically for this computer"), self.p_graphics))
        ll.addWidget(row(tr("Tidy up when Logos closes"), tr("Stops leftover Wine processes"), self.p_tidy))
        self.r_net = row(tr("Internet"), tr("Checks for updates when opened"), self.p_net)
        ll.addWidget(self.r_net)
        ll.addStretch(1)
        both.addWidget(look, 1)
        integ, il = card()
        il.addWidget(label(tr("Integrations"), "h2"))
        self.p_short = pill("", "ok")
        il.addWidget(row(tr("App menu shortcuts"), tr("Logos and Ou Dedetai"),
                         button(tr("Recreate"), None, self.recreate_shortcuts)))
        self.p_desktop = button(tr("Install"), None, self.install_integrations)
        il.addWidget(row(tr("Desktop integrations"), tr("KRunner, look-up shortcut, reading plans, widgets"),
                         self.p_desktop))
        self.p_speech = button(tr("Update"), None, self.update_akousousin)
        il.addWidget(row(tr("Akousousin"), tr("Read Aloud voices and dictation"), self.p_speech))
        il.addStretch(1)
        both.addWidget(integ, 1)
        v.addLayout(both)
        v.addStretch(1)
        return page

    def _tile(self, grid: QtWidgets.QGridLayout, col: int, title: str) -> QtWidgets.QLabel:
        frame, lay = card()
        lay.addWidget(label(title, "muted"))
        value = label("")
        value.setStyleSheet("font-size: 13pt; font-weight: 600;")
        lay.addWidget(value)
        grid.addWidget(frame, 0, col)
        return value

    def _build_settings(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)
        head = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        titles.addWidget(label(tr("Settings"), "title"))
        titles.addWidget(label(tr("What Ou Dedetai sets in Wine for Logos, and why."), "muted"))
        head.addLayout(titles, 1)
        head.addWidget(button(tr("Re-apply settings"), None, self.update_wine_config))
        v.addLayout(head)

        net, nl = card()
        nl.addWidget(label(tr("Internet"), "h2"))
        self.offline = QtWidgets.QCheckBox(tr("Work offline"))
        self.offline.toggled.connect(self.set_offline)
        nl.addWidget(self.offline)
        nl.addWidget(label(tr("Ou Dedetai won't connect to the internet at all: no update checks, no "
                              "downloads. Installing and updating need a connection."), "muted"))
        nl.addWidget(label(tr("Logos has its own offline setting: Program Settings › Internet in Logos."),
                           "muted"))
        v.addWidget(net)

        ws, self.ws_layout = card()
        self.ws_layout.addWidget(label(tr("Wine settings for Logos"), "h2"))
        self.ws_rows = QtWidgets.QVBoxLayout()
        self.ws_layout.addLayout(self.ws_rows)
        v.addWidget(ws)

        self.dev_toggle = QtWidgets.QCheckBox(tr("Show developer and testing options"))
        v.addWidget(self.dev_toggle)
        self.dev, dl = card(accent="warn")
        dl.addWidget(label(tr("Developer and testing options"), "h2"))
        dl.addWidget(label(tr("For testing Wine builds and helping support. Most people never need these."),
                           "muted"))
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.addWidget(label(tr("Graphics renderer")), 0, 0)
        self.renderer = QtWidgets.QComboBox()
        for value, text in (("dxvk", "DXVK"), ("gl", "OpenGL"), ("vulkan", tr("Vulkan (wined3d)")),
                            ("gdi", tr("GDI (no 3D)"))):
            self.renderer.addItem(text, value)
        grid.addWidget(self.renderer, 0, 1)
        grid.addWidget(button(tr("Apply"), None, self.apply_renderer), 0, 2)
        self.renderer_now = label("", "muted")
        grid.addWidget(self.renderer_now, 0, 3)
        grid.addWidget(label(tr("Wine builds to use")), 3, 0)
        self.channel = QtWidgets.QComboBox()
        self.channel.addItem(tr("Prerelease (newest oinos build)"), "dev")
        self.channel.addItem(tr("Stable (newest full release)"), "stable")
        grid.addWidget(self.channel, 3, 1)
        grid.addWidget(button(tr("Apply"), None, self.apply_channel), 3, 2)
        grid.addWidget(label(tr("Then use Update ▸ Wine, or install again."), "muted"), 3, 3)
        grid.addWidget(label(tr("Windows version for Logos")), 1, 0)
        self.winver_logos = QtWidgets.QComboBox()
        grid.addWidget(self.winver_logos, 1, 1)
        grid.addWidget(button(tr("Apply"), None, lambda: self.apply_winver("logos", self.winver_logos)), 1, 2)
        grid.addWidget(label(tr("Windows version for the indexer")), 2, 0)
        self.winver_indexer = QtWidgets.QComboBox()
        grid.addWidget(self.winver_indexer, 2, 1)
        grid.addWidget(button(tr("Apply"), None, lambda: self.apply_winver("indexer", self.winver_indexer)),
                       2, 2)
        for combo in (self.winver_logos, self.winver_indexer):
            combo.addItem(tr("Wine default"), "")
            for version in constants.WINDOWS_VERSIONS:
                if version.startswith("Return"):
                    continue
                combo.addItem(version, version)
        grid.setColumnStretch(3, 1)
        dl.addLayout(grid)
        self.media = QtWidgets.QCheckBox(tr("Experimental media support (video and audiobooks)"))
        self.media.clicked.connect(lambda _=False: self.toggle_media_support())
        dl.addWidget(self.media)
        tools = QtWidgets.QGridLayout()
        for i, (text, slot) in enumerate((
            ("winecfg", lambda: self.run_wine_tool("winecfg")),
            ("winetricks", self.run_winetricks),
            (tr("Registry editor"), lambda: self.run_wine_tool("regedit")),
            (tr("Wine command prompt"), lambda: self.run_wine_tool("wineconsole", ["cmd"])),
            (tr("Run a Windows program…"), self.run_windows_program),
            (tr("Open the prefix folder"), lambda: open_path(self.conf.wine_prefix)),
        )):
            tools.addWidget(button(text, None, slot), i // 3, i % 3)
        dl.addLayout(tools)
        dl.addWidget(label(tr("Command line: oudedetai --show-wine-config, oudedetai --wine winecfg"), "muted"))
        self.dev.setVisible(False)
        self.dev_toggle.toggled.connect(self.dev.setVisible)
        self._show_channel()
        v.addWidget(self.dev)
        v.addStretch(1)
        return page

    def _build_trouble(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(page)
        grid.setContentsMargins(24, 20, 24, 20)
        grid.setSpacing(14)
        grid.addWidget(label(tr("Troubleshooting"), "title"), 0, 0, 1, 2)

        checks, cl = card()
        top = QtWidgets.QHBoxLayout()
        top.addWidget(label(tr("Health checks"), "h2"), 1)
        top.addWidget(button(tr("Check again"), None, self.run_health_checks))
        cl.addLayout(top)
        self.checks_box = QtWidgets.QVBoxLayout()
        cl.addLayout(self.checks_box)
        cl.addStretch(1)
        checks.setMinimumWidth(300)
        grid.addWidget(checks, 1, 0, 4, 1)

        def section(title, items, row_, accent=None, columns=1):
            frame, lay = card(accent)
            lay.addWidget(label(title, "h2"))
            g = QtWidgets.QGridLayout()
            for i, widget in enumerate(items):
                g.addWidget(widget, i // columns, i % columns)
            lay.addLayout(g)
            grid.addWidget(frame, row_, 1)
            return lay

        help_ = section(tr("Getting help"), [
            button(tr("Save a support report…"), "primary", self.get_support),
            button(tr("Open the logs folder"), None, self.open_logs),
        ], 1, accent="true")
        self.logging = QtWidgets.QCheckBox(tr("Logos's own logging (for Faithlife support)"))
        self.logging.clicked.connect(lambda _=False: self.switch_logging())
        help_.addWidget(self.logging)
        section(tr("Repair"), [
            button(tr("Re-apply settings"), None, self.update_wine_config),
            button(tr("Rebuild the index"), None, self.run_indexing),
            button(tr("Remove the library catalog"), None, self.remove_library_catalog),
            button(tr("Remove all index files"), None, self.remove_indexes),
            button(tr("Reinstall language data (ICU)"), None, self.install_icu),
            button(tr("Install dependencies"), None, self.install_deps),
        ], 2)
        section(tr("Your data"), [
            button(tr("Back up…"), None, self.run_backup),
            button(tr("Restore…"), None, self.run_restore),
        ], 3, columns=2)
        section(tr("More"), [
            button(tr("Choose a Wine build (AppImage or tarball)…"), None, self.set_appimage),
            button(tr("Edit the config file…"), None, self.edit_config),
            button(tr("Uninstall Logos…"), "danger", self.uninstall),
        ], 4)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setRowStretch(5, 1)
        return page

    # ── Menus ──
    def _fill_run_menu(self, menu: QtWidgets.QMenu) -> None:
        menu.clear()
        default = menu.addAction(tr("Start as usual"))
        default.triggered.connect(self.run_logos)
        menu.addSeparator()
        for plan in self._plans[:3]:
            for reading in (plan.get("readings") or [])[:2]:
                if reading.get("url"):
                    a = menu.addAction(tr("Today's reading: {reading}").format(
                        reading=reading.get("label") or plan.get("title", "")))
                    a.triggered.connect(lambda _=False, url=reading["url"]: self.open_in_logos(
                        lambda: desktop_integrations.open_url(url)))
        passage = menu.addAction(tr("Open a passage…"))
        passage.triggered.connect(self.ask_passage)
        passage.setEnabled(desktop_integrations.is_installed())
        layouts = menu.addMenu(tr("Saved layouts"))
        if self._layouts:
            for name in self._layouts:
                a = layouts.addAction(name)
                a.triggered.connect(lambda _=False, n=name: self.open_in_logos(
                    lambda: desktop_integrations.open_layout(n), wait_for_com=True))
        else:
            empty = layouts.addAction(tr("None found (needs the desktop integrations)")
                                      if not desktop_integrations.is_installed() else tr("None saved yet"))
            empty.setEnabled(False)
        quick = menu.addMenu(tr("Quick Start layouts"))
        unavailable = quick.addAction(tr("Passage Study (not available yet)"))
        unavailable.setEnabled(False)

    def _update_menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu()
        menu.aboutToShow.connect(lambda m=menu: self._fill_update_menu(m))
        return menu

    def _fill_update_menu(self, menu: QtWidgets.QMenu) -> None:
        menu.clear()
        if network.is_offline():
            a = menu.addAction(tr("Offline mode is on"))
            a.setEnabled(False)
            return
        if not self._updates:
            a = menu.addAction(tr("Checking for updates…"))
            a.setEnabled(False)
            return
        for key, slot in (("wine", self.update_wine), ("app", self.update_to_latest_lli_release),
                          ("logos", self.update_faithlife_product)):
            enabled, text = self._updates.get(key, (False, ""))
            if text:
                a = menu.addAction(text)
                a.setEnabled(enabled)
                a.triggered.connect(slot)

    # ── Refresh ──
    def _refresh_later(self, *_):
        self._dispatch(self.refresh, wait=False)

    def refresh(self) -> None:
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
            title = f"{product} Bible Software" if product == "Logos" else product
            state = tr("Running") if self.logos.logos_state == State.RUNNING else (
                tr("Starting…") if self.logos.logos_state == State.STARTING else tr("Ready"))
            version = self.conf.installed_faithlife_product_release or ""
            state_line = f"{state} · {tr('version {version}').format(version=version)}" if version else state
        else:
            title = tr("Install {product} on Linux").format(product=product)
            state_line = tr("Not installed yet")
        self.s_icon.setPixmap(gui_style.pixmap(icon, 64))
        self.h_icon.setPixmap(gui_style.pixmap(icon, 56))
        self.s_title.setText(title)
        self.h_title.setText(title)
        self.s_state.setText(state_line)
        self.h_state.setText(state_line)
        self.s_install_box.setVisible(not installed)
        self.s_run_box.setVisible(installed)
        self.s_hint.setVisible(installed)
        self.s_full_default.setVisible(installed)
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
        self.h_index.setEnabled(installed and not running)
        self.h_index.setVisible(installed)
        self.h_run.setVisible(installed)
        self.h_install.setVisible(not installed)
        self.h_install.setEnabled(not offline and not self._installing)
        self.s_options.setEnabled(not offline and not self._installing)
        self.s_update.setEnabled(installed)
        # Home tiles
        oinos = self._oinos()
        if not installed:
            self.t_updates.setText("–")
        else:
            self.t_updates.setText(tr("Logos updates itself") if oinos else tr("Ou Dedetai updates Logos"))
        self.t_wine.setText(self._wine_label())
        self.p_links.setText(tr("On"))
        self.p_graphics.setText(renderer_name(wine_settings.renderer_summary(self)) if installed else "–")
        set_pill(self.p_net, tr("Offline") if offline else tr("Online"), "warn" if offline else "off")
        self.offline.blockSignals(True)
        self.offline.setChecked(self.conf.offline_mode)
        self.offline.setEnabled(not self.conf._overrides.offline)
        self.offline.blockSignals(False)
        self.p_desktop.setText(tr("Installed") if desktop_integrations.is_installed() else tr("Install"))
        self.p_desktop.setEnabled(not desktop_integrations.is_installed() and not offline)
        self.p_speech.setEnabled(installed and not offline)
        self.logging.blockSignals(True)
        self.logging.setChecked(bool(self.conf.faithlife_product_logging))
        self.logging.blockSignals(False)
        if installed:
            reports = wine_settings.report_for_app(self)
            needed = [r for r in reports if r.needed and r.setting.group == wine_settings.Group.NEEDED]
            ok = sum(r.state == wine_settings.State.APPLIED for r in needed)
            self.t_settings.setText(tr("All applied") if ok == len(needed) else
                                    tr("{ok} of {total} applied").format(ok=ok, total=len(needed)))
        else:
            self.t_settings.setText("–")

    def _oinos(self) -> bool:
        release = wine_settings.wine_release(self)
        return bool(release and wine.wine_supports_logos_updates(release))

    def _wine_label(self) -> str:
        release = wine_settings.wine_release(self)
        if release is None:
            return "–"
        text = f"{release.major}.{release.minor}"
        return f"{text} (oinos)" if wine.wine_supports_logos_updates(release) else text

    def refresh_settings(self) -> None:
        clear_layout(self.ws_rows)
        if not self.is_installed():
            self.ws_rows.addWidget(label(tr("Install Logos first."), "muted"))
            return
        reports = wine_settings.report_for_app(self)
        groups = [
            (wine_settings.Group.NEEDED, tr("Needed for Logos")),
            (wine_settings.Group.REVIEW, tr("Being reviewed")),
        ]
        for group, title in groups:
            rows = [r for r in reports if r.setting.group == group and r.needed]
            if not rows:
                continue
            self.ws_rows.addWidget(label(title.upper(), "group"))
            for r in rows:
                kind, text = {
                    wine_settings.State.APPLIED: ("ok", tr("Applied")),
                    wine_settings.State.DIFFERENT: ("warn", tr("Different")),
                    wine_settings.State.MISSING: ("warn", tr("Not set")),
                    wine_settings.State.UNKNOWN: ("off", tr("Unknown")),
                }[r.state]
                if group == wine_settings.Group.REVIEW and r.state == wine_settings.State.APPLIED:
                    kind, text = "warn", tr("Under review")
                w = row(tr(r.setting.title), tr(r.setting.reason), pill(text, kind))
                if r.details:
                    w.setToolTip("\n".join(r.details))
                self.ws_rows.addWidget(w)
        skipped = [r for r in reports if not r.needed]
        if skipped:
            self.ws_rows.addWidget(label(tr("Not needed with this Wine").upper(), "group"))
            for r in skipped:
                self.ws_rows.addWidget(row(tr(r.setting.title), tr(r.setting.reason), pill(tr("Skipped"), "off")))
        renderer = wine_settings.renderer_summary(self)
        self.renderer_now.setText(tr("Now: {renderer}").format(renderer=renderer_name(renderer)))
        index = self.renderer.findData(renderer)
        if index >= 0:
            self.renderer.setCurrentIndex(index)
        self.media.setChecked(wine.media_support_enabled(self))
        self._show_channel()

        def load_winver():
            versions = (wine.get_win_version(self, "logos") or "", wine.get_win_version(self, "indexer") or "")

            def show():
                for combo, value in zip((self.winver_logos, self.winver_indexer), versions):
                    i = combo.findData(value)
                    combo.setCurrentIndex(i if i >= 0 else 0)
            self._dispatch(show, wait=False)
        if self.dev_toggle.isChecked():
            self.start_thread(load_winver)
        else:
            self.dev_toggle.toggled.connect(lambda on: on and self.start_thread(load_winver))

    def run_health_checks(self) -> None:
        clear_layout(self.checks_box)
        self.checks_box.addWidget(label(tr("Checking…"), "muted"))

        def check() -> list[tuple[bool, str, str]]:
            results: list[tuple[bool, str, str]] = []
            installed = self.is_installed()
            results.append((installed, tr("Logos is installed"),
                            self.conf.logos_exe or tr("Not installed yet")))
            if installed:
                self.logos.monitor()
                leftover = self.logos.logos_state == State.STOPPED and bool(leftover_wine(self.conf.wine_prefix))
                results.append((not leftover, tr("No Wine left running"),
                                tr("A Wine server from an earlier session is still running") if leftover
                                else tr("Nothing left over")))
                reports = wine_settings.report_for_app(self)
                missing = [r.setting.title for r in reports if r.needed
                           and r.setting.group == wine_settings.Group.NEEDED
                           and r.state != wine_settings.State.APPLIED]
                results.append((not missing, tr("Wine settings"),
                                tr("All applied") if not missing else tr("Not applied: {names}").format(
                                    names=", ".join(missing))))
            try:
                ok, message = system.check_opengl_version(self)
                results.append((ok, tr("Graphics (OpenGL)"), message))
            except Exception as error:
                results.append((False, tr("Graphics (OpenGL)"), str(error)))
            results.append((True, tr("Internet"), tr("Offline mode is on") if network.is_offline()
                            else tr("Online")))
            results.append((desktop_integrations.is_installed(), tr("Desktop integrations"),
                            tr("Installed") if desktop_integrations.is_installed() else tr("Not installed")))
            return results

        def show(results):
            clear_layout(self.checks_box)
            for ok, title, detail in results:
                left = pill(tr("OK") if ok else tr("Check"), "ok" if ok else "warn")
                left.setMinimumWidth(56)
                left.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                right = None
                if not ok and title == tr("No Wine left running"):
                    right = button(tr("End them"), None, self.end_leftover_wine)
                self.checks_box.addWidget(row(title, str(detail), right, left))

        self.start_thread(lambda: (lambda r: self._dispatch(lambda: show(r), wait=False))(check()))

    def _render_reading(self) -> None:
        clear_layout(self.reading_body)
        plan = next((p for p in self._plans if p.get("readings")), None)
        self.reading_card.setVisible(plan is not None)
        if plan is None:
            return
        self.reading_plan.setText(plan.get("status") or plan.get("title", ""))
        title = label(plan.get("title", ""))
        title.setStyleSheet("font-weight: 600;")
        self.reading_body.addWidget(title)
        for reading in plan.get("readings", [])[:5]:
            b = button(reading.get("label") or reading.get("short") or "", "link",
                       lambda url=reading.get("url"): self.open_in_logos(lambda: desktop_integrations.open_url(url)))
            self.reading_body.addWidget(b)
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(round(100 * float(plan.get("progress") or 0))))
        bar.setTextVisible(False)
        bar.setMaximumHeight(6)
        bar.setAccessibleName(tr("Plan progress"))
        self.reading_body.addWidget(bar)
        self.reading_body.addWidget(label(tr("Mark readings done in Logos."), "muted"))

    # ── Background work ──
    def _monitor(self) -> None:
        last = None
        while True:
            if self.is_installed():
                self.logos.monitor()
            state = self.logos.logos_state
            if state != last:
                last = state
                self._refresh_later()
            time.sleep(1 if self.is_installed() else 10)

    def _load_integrations(self) -> None:
        if not desktop_integrations.is_installed():
            return
        plans = desktop_integrations.reading_plans()
        layouts = desktop_integrations.saved_layouts()

        def show():
            self._plans, self._layouts = plans, layouts
            self._render_reading()
        self._dispatch(show, wait=False)

    def _check_updates(self) -> None:
        if network.is_offline() or not self.is_installed():
            return
        updates: dict[str, tuple[bool, str]] = {}
        try:
            status, _ = utils.compare_recommended_wine_version(self)
            updates["wine"] = (status == 0, tr("Update Wine to the recommended build") if status == 0
                               else tr("Wine is up to date"))
        except Exception:
            logging.debug("Wine update check failed", exc_info=True)
        try:
            result = utils.compare_logos_linux_installer_version(self)
            can = constants.RUNMODE == "binary" and result == utils.VersionComparison.OUT_OF_DATE
            updates["app"] = (can, tr("Update Ou Dedetai to {version}").format(version=self.conf.app_latest_version)
                              if can else tr("Ou Dedetai is up to date"))
        except Exception:
            logging.debug("Ou Dedetai update check failed", exc_info=True)
        if self._oinos():
            updates["logos"] = (False, tr("Logos updates itself"))
        else:
            try:
                latest = self.conf.is_installed_faithlife_product_release_latest
                updates["logos"] = (not latest, tr("Update Logos") if not latest else tr("Logos is up to date"))
            except Exception:
                logging.debug("Logos update check failed", exc_info=True)
        self._updates = updates

    def open_in_logos(self, action: Callable[[], object], wait_for_com: bool = False) -> None:
        """Start Logos if needed, then do something in it (open a link or layout)."""
        def run():
            if self.logos.logos_state not in (State.RUNNING, State.STARTING):
                self.logos.start()
            deadline = time.monotonic() + 240
            while self.logos.logos_state != State.RUNNING and time.monotonic() < deadline:
                time.sleep(1)
                self.logos.monitor()
            if wait_for_com:
                time.sleep(10)  # COM answers once Logos has finished opening its window
            action()
        self.start_thread(run)

    def ask_passage(self) -> None:
        text, ok = QtWidgets.QInputDialog.getText(self.root, tr("Open a passage"),
                                                  tr("Bible reference, e.g. John 3:16 or Rom 8:28-30"))
        if ok and text.strip():
            self.open_in_logos(lambda: desktop_integrations.open_reference(text.strip()))

    # ── Actions (existing operations) ──
    def _set_product(self, product: str) -> None:
        if self.conf._raw.faithlife_product != product:
            self.conf.faithlife_product = product
            self.populate_defaults()

    def _install_from_full(self) -> None:
        self.show_view(SIMPLE)
        self.run_install()

    def _after_change(self) -> None:
        self.refresh()
        self.refresh_settings()

    def run_install(self) -> None:
        self._installing = True
        self.guide.set_product(self.conf._raw.faithlife_product or constants.FAITHLIFE_PRODUCTS[0],
                               self.conf.faithlife_product_icon_path)
        self.show_view(INSTALLING)

        def install():
            try:
                self.populate_defaults()
                installer.install(self)
            except Exception:
                logging.exception("Install failed")
            finally:
                self._installing = False
                self._dispatch(self._install_finished, wait=False)
        self.start_thread(install)

    def _install_finished(self) -> None:
        self.show_view(SIMPLE)
        self.refresh()

    def run_installer(self) -> None:
        dialog = Toplevel(self.root)
        window = InstallerWindow(dialog, self.root, self)
        # The options dialog closes itself and starts installer.install; show the guide too.
        window.gui.okay_button.clicked.connect(lambda: self._dispatch(self._begin_guide, wait=False))
        dialog.exec()

    def _begin_guide(self) -> None:
        self._installing = True
        self.guide.set_product(self.conf.faithlife_product, self.conf.faithlife_product_icon_path)
        self.show_view(INSTALLING)

    def run_logos(self) -> None:
        self.start_thread(self.logos.start)

    def stop_logos(self) -> None:
        self.start_thread(self.logos.stop)

    def run_indexing(self) -> None:
        self.start_thread(self.logos.index)

    def end_leftover_wine(self) -> None:
        self.start_thread(lambda: (wine.wineserver_kill(self), self._dispatch(self.run_health_checks, wait=False)))

    def remove_library_catalog(self) -> None:
        self.start_thread(control.remove_library_catalog, self)

    def remove_indexes(self) -> None:
        self.start_thread(control.remove_all_index_files, app=self)

    def install_icu(self) -> None:
        self.start_thread(wine.enforce_icu_data_files, app=self)

    def install_deps(self) -> None:
        self.start_thread(utils.install_dependencies, self)

    def uninstall(self) -> None:
        def run():
            control.uninstall(self)
            self.clear_status()
            self.populate_defaults()
            self._refresh_later()
        self.start_thread(run)

    def run_backup(self) -> None:
        self.start_thread(backup.backup, app=self)

    def run_restore(self) -> None:
        self.start_thread(backup.restore, app=self)

    def update_akousousin(self) -> None:
        self.start_thread(system.update_akousousin, self)

    def update_wine_config(self) -> None:
        def run():
            installer.update_wine_config(self)
            self._dispatch(self._after_change, wait=False)
        self.start_thread(run)

    def recreate_shortcuts(self) -> None:
        self.start_thread(installer.create_launcher_shortcuts, self)

    def install_integrations(self) -> None:
        def run():
            desktop_integrations.install(self)
            self._load_integrations()
            self._refresh_later()
        self.start_thread(run)

    def update_faithlife_product(self) -> None:
        self.start_thread(utils.update_faithlife_product, app=self)

    def update_to_latest_lli_release(self) -> None:
        self.start_thread(utils.update_to_latest_lli_release, app=self)

    def update_wine(self) -> None:
        self.start_thread(installer.update_to_latest_wine, self)

    def set_appimage(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.root, tr("Choose a Wine build"), str(Path.home()),
            tr("Wine runner (*.AppImage *.tar.xz *.tar.gz *.tgz);;All files (*)"))
        if filename:
            self.conf.wine_appimage_path = filename
            self.start_thread(utils.set_appimage_symlink, self)

    def edit_config(self) -> None:
        control.edit_file(self.conf.config_file_path)

    def get_support(self) -> None:
        self.start_thread(control.get_support, self)

    def open_logs(self) -> None:
        open_path(Path(self.conf.app_log_path).parent)

    def switch_logging(self) -> None:
        action = "enable" if self.logging.isChecked() else "disable"
        self.start_thread(self.logos.switch_logging, action=action)

    def toggle_media_support(self) -> None:
        def run():
            wine.toggle_media_support(self)
            self._dispatch(self.refresh_settings, wait=False)
        self.start_thread(run)

    def apply_renderer(self) -> None:
        choice = self.renderer.currentData()

        def run():
            message = wine.select_renderer(self, choice)
            self.status(message)
            self._dispatch(self._after_change, wait=False)
        self.start_thread(run)

    def apply_winver(self, exe: str, combo: QtWidgets.QComboBox) -> None:
        version = combo.currentData()
        if version:
            self.start_thread(wine.set_win_version, self, exe, version)

    def _show_channel(self) -> None:
        i = self.channel.findData(self.conf.wine_release_channel)
        self.channel.setCurrentIndex(i if i >= 0 else 0)

    def apply_channel(self) -> None:
        self.conf.wine_release_channel = self.channel.currentData()
        self._updates = {}
        self.start_thread(self._check_updates)

    def set_offline(self, on: bool) -> None:
        self.conf.offline_mode = on
        self.refresh()
        if not on:
            self.start_thread(self._check_updates)

    def run_wine_tool(self, exe: str, args: Optional[list[str]] = None) -> None:
        def run():
            with open(os.devnull, "w") as devnull:
                wine.run_wine_process(self, self.conf.wine64_binary, devnull, devnull,
                                      exe=exe, exe_args=args or [])
        self.start_thread(run)

    def run_winetricks(self) -> None:
        def run():
            try:
                binary = self.conf.winetricks_binary  # fetched once if missing (not in offline mode)
            except Exception as error:
                self.status(tr("winetricks isn't available: {error}").format(error=error))
                return
            if not Path(binary).exists():
                self.status(tr("winetricks isn't available with this Wine build."))
                return
            subprocess.Popen([binary], env=wine.get_wine_env(self), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.start_thread(run)

    def run_windows_program(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.root, tr("Run a Windows program"), str(Path.home()),
            tr("Windows programs (*.exe *.msi);;All files (*)"))
        if filename:
            self.run_wine_tool(filename)


# ── Tray (while Logos runs from its shortcut) ────────────────────────────────

class TrayController(QtCore.QObject):
    """Ou Dedetai in the system tray while Logos runs; leaves when Logos closes."""

    def __init__(self, window: MainWindow, qt_app: QtWidgets.QApplication):
        super().__init__()
        self.window = window
        self.qt_app = qt_app
        self.seen_running = False
        self.tray: Optional[QtWidgets.QSystemTrayIcon] = None
        if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QtWidgets.QSystemTrayIcon(gui_style.app_icon())
            self.tray.setToolTip(constants.APP_NAME)
            menu = QtWidgets.QMenu()
            menu.aboutToShow.connect(lambda: self._fill(menu))
            self._fill(menu)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._activated)
            self.tray.show()
        else:
            logging.info("No system tray on this desktop: Ou Dedetai runs in the background without an icon.")
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(3000)

    def _fill(self, menu: QtWidgets.QMenu) -> None:
        menu.clear()
        state = self.window.logos.logos_state
        head = menu.addAction(tr("Logos is running") if state == State.RUNNING else tr("Logos is starting…"))
        head.setEnabled(False)
        w = self.window
        for plan in w._plans[:2]:
            for reading in (plan.get("readings") or [])[:1]:
                if reading.get("url"):
                    a = menu.addAction(tr("Today's reading: {reading}").format(reading=reading.get("label", "")))
                    a.triggered.connect(lambda _=False, url=reading["url"]: w.start_thread(
                        desktop_integrations.open_url, url))
        if w._layouts:
            layouts = menu.addMenu(tr("Open layout"))
            for name in w._layouts:
                a = layouts.addAction(name)
                a.triggered.connect(lambda _=False, n=name: w.start_thread(desktop_integrations.open_layout, n))
        stop = menu.addAction(tr("Stop Logos"))
        stop.triggered.connect(w.stop_logos)
        menu.addSeparator()
        show = menu.addAction(tr("Ou Dedetai…"))
        show.triggered.connect(lambda: self.show_window(SIMPLE))
        trouble = menu.addAction(tr("Troubleshooting…"))
        trouble.triggered.connect(lambda: self.show_window(FULL, TROUBLE))

    def _activated(self, reason) -> None:
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
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


# ── Entry points ─────────────────────────────────────────────────────────────

def _qt_app() -> QtWidgets.QApplication:
    existing = QtWidgets.QApplication.instance()
    app = existing if isinstance(existing, QtWidgets.QApplication) else \
        QtWidgets.QApplication([constants.BINARY_NAME])
    app.setApplicationName(constants.APP_NAME)
    app.setDesktopFileName(constants.BINARY_NAME)
    load_translation(app)
    gui_style.apply(app)
    return app


_translator: Optional[QtCore.QTranslator] = None


def load_translation(app: QtWidgets.QApplication) -> None:
    """Load the GUI translation for the user's language, if there is one (Spanish so far)."""
    global _translator
    locale = QtCore.QLocale.system()
    translator = QtCore.QTranslator(app)
    folder = str(Path(__file__).parent / "i18n")
    if translator.load(locale, "oudedetai", "_", folder):
        app.installTranslator(translator)
        _translator = translator


def start(ephemeral_config: EphemeralConfiguration, install: bool = False) -> int:
    """The window (control panel). With ``install``, start installing straight away."""
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
    window.start_thread(window.logos.start)
    tray = TrayController(window, app)  # noqa: F841 (kept alive by the event loop)
    app._od_tray = tray  # type: ignore[attr-defined]
    return app.exec()


def display_available() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


