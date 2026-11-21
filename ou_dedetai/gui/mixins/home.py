"""The Home page."""
import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from ... import desktop_integrations, wine_settings
from ..blocks import SETTINGS, button, card, label, pill, renderer_name, row, set_pill
from ..style import tr
from .base import WindowBase


class HomePageMixin(WindowBase):
    """The Home page and its tiles."""

    def _build_home(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)
        hero, hl = card(accent="true")
        top = QHBoxLayout()
        self.h_icon = QLabel()
        top.addWidget(self.h_icon)
        col = QVBoxLayout()
        self.h_title = label("", "title")
        self.h_state = label("", "muted")
        col.addWidget(self.h_title)
        col.addWidget(self.h_state)
        top.addLayout(col, 1)
        self.h_stop = button(tr("Stop"), None, self.stop_logos)
        self.h_stop.setMinimumHeight(40)
        top.addWidget(self.h_stop)
        self.h_update = QToolButton()
        self.h_update.setText(tr("Update"))
        self.h_update.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.h_update.setMenu(self._update_menu())
        self.h_update.setMinimumHeight(40)
        top.addWidget(self.h_update)
        self.h_run = self._run_button()
        top.addWidget(self.h_run)
        self.h_install = button(tr("Install"), "primary", self._install_from_full)
        self.h_install.setMinimumHeight(40)
        top.addWidget(self.h_install)
        hl.addLayout(top)
        v.addWidget(hero)

        tiles = QGridLayout()
        tiles.setSpacing(12)
        self.t_updates = self._tile(tiles, 0, tr("Logos updates"))
        self.t_wine = self._tile(tiles, 1, tr("Wine"))
        self.t_settings = self._tile(tiles, 2, tr("Wine settings for Logos"))
        self.t_settings.setTextFormat(Qt.TextFormat.RichText)  # "Not yet: …" on a smaller line
        see = button(tr("See the list…"), "link", lambda: self.show_page(SETTINGS))
        tile = self.t_settings.parentWidget()
        tile_layout = tile.layout() if tile is not None else None
        if tile_layout is not None:
            tile_layout.addWidget(see)
        v.addLayout(tiles)

        both = QHBoxLayout()
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
        ll.addWidget(row(tr("Tidy up before Logos starts"), tr("Stops Wine left running from earlier"), self.p_tidy))
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
        il.addWidget(self._akousousin_row())
        il.addStretch(1)
        both.addWidget(integ, 1)
        v.addLayout(both)
        v.addStretch(1)
        return page

    def _tile(self, grid: QGridLayout, col: int, title: str) -> QLabel:
        frame, lay = card()
        lay.addWidget(label(title, "muted"))
        value = label("", "value")
        lay.addWidget(value)
        grid.addWidget(frame, 0, col)
        return value

    def _refresh_home(self, installed: bool, offline: bool) -> None:
        oinos = self._oinos()
        if not installed:
            self.t_updates.setText("–")
        else:
            self.t_updates.setText(tr("Logos updates itself") if oinos else tr("Ou Dedetai updates Logos"))
        self.t_wine.setText(self._wine_label())
        self.p_links.setText(tr("On"))
        self.p_graphics.setText(renderer_name(wine_settings.renderer_summary(self)) if installed else "–")
        set_pill(self.p_net, tr("Offline") if offline else tr("Online"), "warn" if offline else "off")
        self.t_integrations.setVisible(desktop_integrations.is_installed())
        self.t_integrations.setEnabled(not offline)
        if installed:
            reports = wine_settings.report_for_app(self)
            needed = [r for r in reports if r.needed and r.setting.group == wine_settings.Group.NEEDED]
            ok = sum(r.state == wine_settings.State.APPLIED for r in needed)
            missing = [tr(r.setting.title) for r in needed if r.state != wine_settings.State.APPLIED]
            if not missing:
                self.t_settings.setText(tr("All {total} needed are applied").format(total=len(needed)))
            else:
                # Say which, not just how many (details under Settings → Wine settings).
                self.t_settings.setText(
                    tr("{ok} of {total} needed are applied").format(ok=ok, total=len(needed))
                    + "<br><span style='font-size: 9pt; font-weight: 400;'>"
                    + tr("Not yet: {names}").format(names=html.escape(", ".join(missing))) + "</span>")
        else:
            self.t_settings.setText("–")
