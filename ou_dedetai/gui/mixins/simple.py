"""The simple view."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QMenu, QRadioButton, QToolButton, QVBoxLayout, QWidget

from ... import constants
from ..blocks import HOME, button, label
from ..style import tr
from .base import WindowBase


class SimpleViewMixin(WindowBase):
    """The simple view: Install, or Run / Update / Stop."""

    def _build_simple(self) -> QWidget:
        page = QWidget()
        page.setObjectName("od-page")
        v = QVBoxLayout(page)
        v.setContentsMargins(40, 28, 40, 16)
        v.setSpacing(18)

        head = QHBoxLayout()
        self.s_icon = QLabel()
        head.addWidget(self.s_icon)
        titles = QVBoxLayout()
        self.s_title = label("", "title")
        self.s_state = label("", "muted")
        titles.addWidget(self.s_title)
        titles.addWidget(self.s_state)
        head.addLayout(titles, 1)
        v.addLayout(head)

        self.s_install_box = QWidget()
        ib = QVBoxLayout(self.s_install_box)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.setSpacing(12)
        ib.addWidget(label(tr("Ou Dedetai sets up Wine and installs Logos for you. "
                              "You'll sign in to your Faithlife account at the end."), "muted"))
        products = QHBoxLayout()
        self.s_products = QButtonGroup(page)
        for name in constants.FAITHLIFE_PRODUCTS:
            r = QRadioButton(name)
            r.toggled.connect(lambda on, n=name: self._set_product(n) if on else None)
            self.s_products.addButton(r)
            products.addWidget(r)
        products.addStretch(1)
        ib.addLayout(products)
        self.s_install = button(tr("Install"), "primary", self.run_install)
        self.s_install.setMinimumHeight(44)
        ib.addWidget(self.s_install)
        opts = QHBoxLayout()
        self.s_needs = label("", "muted")
        opts.addWidget(self.s_needs, 1)
        self.s_options = button(tr("Choose options…"), "link", self.run_installer)
        opts.addWidget(self.s_options)
        ib.addLayout(opts)
        v.addWidget(self.s_install_box)

        self.s_run_box = QWidget()
        rb = QHBoxLayout(self.s_run_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(12)
        self.s_run = self._run_button()
        rb.addWidget(self.s_run)
        self.s_update = QToolButton()
        self.s_update.setText(tr("Update"))
        self.s_update.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.s_update.setMenu(self._update_menu())
        rb.addWidget(self.s_update)
        self.s_stop = button(tr("Stop"), None, self.stop_logos)
        rb.addWidget(self.s_stop)
        rb.addStretch(1)
        v.addWidget(self.s_run_box)

        self.s_hint = label(tr("The arrow next to Run opens your Bible, today's reading or a "
                               "saved layout. While Logos runs, Ou Dedetai sits in the system tray."), "muted")
        v.addWidget(self.s_hint)
        v.addSpacing(8)
        foot = QHBoxLayout()
        foot.addWidget(button(tr("Full view and settings…"), "link", lambda: self.open_full(HOME)))
        foot.addStretch(1)
        foot.addWidget(label(tr("Ou Dedetai {version} · community supported").format(
            version=constants.LLI_CURRENT_VERSION), "muted", wrap=False))
        v.addLayout(foot)
        return page

    def _run_button(self) -> QToolButton:
        b = QToolButton()
        b.setProperty("kind", "primary")
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        b.setMinimumHeight(40)
        b.clicked.connect(self.run_logos)
        menu = QMenu(b)
        menu.aboutToShow.connect(lambda m=menu: self._fill_run_menu(m))
        b.setMenu(menu)
        b.setAccessibleName(tr("Run Logos"))
        b.setAccessibleDescription(tr("The arrow offers more ways to start Logos"))
        return b

    def _fill_run_menu(self, menu: QMenu) -> None:
        menu.clear()
        menu.addAction(tr("Start as usual")).triggered.connect(self.run_logos)
        menu.addSeparator()
        self.add_open_items(menu)
