"""The Settings page."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QRadioButton, QVBoxLayout, QWidget

from ... import constants, control, network, wine, wine_settings
from ..blocks import button, card, clear_layout, label, open_path, pill, renderer_name, row
from ..style import tr
from .base import WindowBase


class SettingsMixin(WindowBase):
    """The Settings page: offline mode, updates channel, Wine settings and developer options."""

    def _build_settings(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label(tr("Settings"), "title"))
        titles.addWidget(label(tr("What Ou Dedetai sets in Wine for Logos, and why."), "muted"))
        head.addLayout(titles, 1)
        head.addWidget(self.closed_only(button(tr("Re-apply settings"), None, self.update_wine_config)))
        v.addLayout(head)

        net, nl = card()
        nl.addWidget(label(tr("Internet"), "h2"))
        self.offline = QCheckBox(tr("Work offline"))
        self.offline.setProperty("role", "strong")
        self.offline.toggled.connect(self.set_offline)
        nl.addWidget(self.offline)
        nl.addWidget(label(tr("Ou Dedetai won't connect to the internet at all: no update checks, no "
                              "downloads. Installing and updating need a connection."), "muted"))
        nl.addWidget(label(tr("Logos has its own offline setting: Program Settings › Internet in Logos."),
                           "muted"))
        v.addWidget(net)

        upd, ul = card()
        ul.addWidget(label(tr("Updates"), "h2"))
        self.s_releases = QRadioButton(tr("Releases"))
        self.s_prereleases = QRadioButton(tr("Prereleases: help test the next version of "
                                                        "Ou Dedetai and Wine"))
        for b in (self.s_releases, self.s_prereleases):
            ul.addWidget(b)
        self.s_prereleases.toggled.connect(self.set_update_channel)
        ul.addWidget(label(tr("Switching back to Releases doesn't take you back: you stay on the version "
                              "you have until a release catches up."), "muted"))
        v.addWidget(upd)

        ws, self.ws_layout = card()
        self.ws_layout.addWidget(label(tr("Wine settings for Logos"), "h2"))
        self.ws_rows = QVBoxLayout()
        self.ws_layout.addLayout(self.ws_rows)
        v.addWidget(ws)

        win, wl = card()
        wl.addWidget(label(tr("Ou Dedetai window"), "h2"))
        self.s_full_default = QCheckBox(
            tr("Open the full view when Ou Dedetai starts (reading plan, layouts, status)"))
        self.s_full_default.toggled.connect(lambda on: setattr(self.conf, "gui_full_view", on))
        wl.addWidget(self.s_full_default)
        v.addWidget(win)

        self.dev_toggle = QCheckBox(tr("Show developer and testing options"))
        v.addWidget(self.dev_toggle)
        self.dev, dl = card(accent="warn")
        dl.addWidget(label(tr("Developer and testing options"), "h2"))
        dl.addWidget(label(tr("For testing Wine builds and helping support. Most people never need these."),
                           "muted"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.addWidget(label(tr("Graphics renderer")), 0, 0)
        self.renderer = QComboBox()
        for value, text in (("dxvk", "DXVK"), ("gl", "OpenGL"), ("vulkan", tr("Vulkan (wined3d)")),
                            ("gdi", tr("GDI (no 3D)"))):
            self.renderer.addItem(text, value)
        grid.addWidget(self.renderer, 0, 1)
        grid.addWidget(self.closed_only(button(tr("Apply"), None, self.apply_renderer)), 0, 2)
        self.renderer_now = label("", "muted")
        grid.addWidget(self.renderer_now, 0, 3)
        grid.addWidget(label(tr("Wine builds to use")), 3, 0)
        self.channel = QComboBox()
        self.channel.addItem(tr("Prerelease (newest oinos build)"), "dev")
        self.channel.addItem(tr("Stable (newest full release)"), "stable")
        grid.addWidget(self.channel, 3, 1)
        grid.addWidget(button(tr("Apply"), None, self.apply_channel), 3, 2)
        grid.addWidget(label(tr("Then use Update ▸ Wine, or install again."), "muted"), 3, 3)
        grid.addWidget(label(tr("Windows version for Logos")), 1, 0)
        self.winver_logos = QComboBox()
        grid.addWidget(self.winver_logos, 1, 1)
        grid.addWidget(self.closed_only(button(tr("Apply"), None,
                                               lambda: self.apply_winver("logos", self.winver_logos))), 1, 2)
        grid.addWidget(label(tr("Windows version for the indexer")), 2, 0)
        self.winver_indexer = QComboBox()
        grid.addWidget(self.winver_indexer, 2, 1)
        grid.addWidget(self.closed_only(button(tr("Apply"), None,
                                               lambda: self.apply_winver("indexer", self.winver_indexer))), 2, 2)
        for combo in (self.winver_logos, self.winver_indexer):
            combo.addItem(tr("Wine default"), "")
            for version in constants.WINDOWS_VERSIONS:
                if version.startswith("Return"):
                    continue
                combo.addItem(version, version)
        grid.setColumnStretch(3, 1)
        dl.addLayout(grid)
        tools = QGridLayout()
        for i, (text, slot) in enumerate((
            ("winecfg", lambda: self.run_wine_tool("winecfg")),
            ("winetricks", self.run_winetricks),
            (tr("Registry editor"), lambda: self.run_wine_tool("regedit")),
            (tr("Wine command prompt"), lambda: self.run_wine_tool("wineconsole", ["cmd"])),
            (tr("Run a Windows program…"), self.run_windows_program),
            (tr("Open the prefix folder"), lambda: open_path(self.conf.wine_prefix)),
        )):
            tool = button(text, None, slot)
            if text == "winetricks":  # installs into the prefix
                self.closed_only(tool)
            tools.addWidget(tool, i // 3, i % 3)
        dl.addLayout(tools)
        dl.addWidget(label(tr("Command line: oudedetai --show-wine-config, oudedetai --wine winecfg"), "muted"))
        self.dev.setVisible(False)
        self.dev_toggle.toggled.connect(self.dev.setVisible)
        self.dev_toggle.toggled.connect(self._dev_toggled)
        self._show_channel()
        v.addWidget(self.dev)
        v.addStretch(1)
        return page

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
            applied = sum(r.state == wine_settings.State.APPLIED for r in rows)
            self.ws_rows.addWidget(label(f"{title.upper()} · {applied}/{len(rows)}", "group"))
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
        self._show_channel()

        if self.dev_toggle.isChecked():
            self.start_thread(self._load_winver)

    def _refresh_switches(self) -> None:
        self.offline.blockSignals(True)
        self.offline.setChecked(self.conf.offline_mode)
        self.offline.setEnabled(not self.conf._overrides.offline)
        self.offline.blockSignals(False)

    def _dev_toggled(self, on: bool) -> None:
        if on:
            self.start_thread(self._load_winver)

    def _load_winver(self) -> None:
        if wine_settings.configured_wine_binary(self) is None:
            return  # nothing to ask yet (and asking would prompt for a Wine build)
        self.signals.winver.emit(wine.get_win_version(self, "logos") or "",
                                 wine.get_win_version(self, "indexer") or "")

    def _show_winver(self, logos: str, indexer: str) -> None:
        for combo, value in zip((self.winver_logos, self.winver_indexer), (logos, indexer)):
            i = combo.findData(value)
            combo.setCurrentIndex(i if i >= 0 else 0)

    def edit_config(self) -> None:
        control.edit_file(self.conf.config_file_path)

    def apply_renderer(self) -> None:
        choice = self.renderer.currentData()

        def run():
            message = wine.select_renderer(self, choice)
            self.status(message)
            self.signals.settings_changed.emit()
        self.start_thread(run)

    def apply_winver(self, exe: str, combo: QComboBox) -> None:
        version = combo.currentData()
        if version:
            self.start_thread(wine.set_win_version, self, exe, version)

    def _show_channel(self) -> None:
        i = self.channel.findData(self.conf.wine_release_channel)
        self.channel.setCurrentIndex(i if i >= 0 else 0)
        button = self.s_prereleases if self.conf.update_channel == "dev" else self.s_releases
        self.s_releases.blockSignals(True)
        self.s_prereleases.blockSignals(True)
        button.setChecked(True)
        self.s_releases.blockSignals(False)
        self.s_prereleases.blockSignals(False)

    def set_update_channel(self, prereleases: bool) -> None:
        channel = "dev" if prereleases else "stable"
        if self.conf.update_channel == channel and self.conf._raw.update_channel_chosen:
            return
        self.conf.update_channel = channel
        self._show_channel()
        self._updates = {}
        if not network.is_offline():
            self.start_thread(self._check_updates)

    def apply_channel(self) -> None:
        self.conf.wine_release_channel = self.channel.currentData()
        self._updates = {}
        self.start_thread(self._check_updates)

    def set_offline(self, on: bool) -> None:
        self.conf.offline_mode = on
        self.refresh()
        if not on:
            self.start_thread(self._check_updates)
