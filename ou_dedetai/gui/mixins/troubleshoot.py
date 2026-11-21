"""The Troubleshooting page."""
import os
import subprocess
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ... import backup, control, desktop_integrations, network, system, utils, wine, wine_settings
from ...logos import State
from ..blocks import button, card, clear_layout, label, open_path, pill, row
from ..style import tr
from .base import WindowBase


class TroubleshootMixin(WindowBase):
    """The Troubleshooting page: health checks, repairs, logs and Wine tools."""

    def _build_trouble(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(24, 20, 24, 20)
        grid.setSpacing(14)
        grid.addWidget(label(tr("Troubleshooting"), "title"), 0, 0, 1, 2)

        checks, cl = card()
        top = QHBoxLayout()
        top.addWidget(label(tr("Health checks"), "h2"), 1)
        top.addWidget(button(tr("Check again"), None, self.run_health_checks))
        cl.addLayout(top)
        self.checks_box = QVBoxLayout()
        cl.addLayout(self.checks_box)
        cl.addStretch(1)
        checks.setMinimumWidth(300)
        grid.addWidget(checks, 1, 0, 4, 1)

        def section(title, items, row_, accent=None, columns=1):
            frame, lay = card(accent)
            lay.addWidget(label(title, "h2"))
            g = QGridLayout()
            for i, widget in enumerate(items):
                g.addWidget(widget, i // columns, i % columns)
            lay.addLayout(g)
            grid.addWidget(frame, row_, 1)
            return lay

        help_ = section(tr("Getting help"), [
            button(tr("Save a support report…"), "primary", self.get_support),
            button(tr("Open the logs folder"), None, self.open_logs),
        ], 1, accent="true")
        self.logging = self.closed_only(QCheckBox(tr("Logos's own logging (for Faithlife support)")))
        self.logging.clicked.connect(lambda _=False: self.switch_logging())
        help_.addWidget(self.logging)
        # An OS update (seen on Bazzite and SteamOS) can leave KRunner and the look-up
        # shortcut not working; reinstalling them puts their files and settings back (#581).
        self.t_integrations = button(tr("Reinstall desktop integrations"), None, self.install_integrations)
        self.t_reindex = self.closed_only(button(tr("Rebuild the index"), None, self.run_indexing))
        section(tr("Repair"), [
            self.closed_only(button(tr("Re-apply settings"), None, self.update_wine_config)),
            self.t_integrations,
            self.t_reindex,
            self.closed_only(button(tr("Remove the library catalog"), None, self.remove_library_catalog)),
            self.closed_only(button(tr("Remove all index files"), None, self.remove_indexes)),
            self.closed_only(button(tr("Reinstall language data (ICU)"), None, self.install_icu)),
            button(tr("Install dependencies"), None, self.install_deps),
        ], 2)
        section(tr("Your data"), [
            self.closed_only(button(tr("Back up…"), None, self.run_backup)),
            self.closed_only(button(tr("Restore…"), None, self.run_restore)),
        ], 3, columns=2)
        section(tr("More"), [
            self.closed_only(self._wine_build_button()),
            button(tr("Check for updates now"), None, self.check_updates_now),
            button(tr("Edit the config file…"), None, self.edit_config),
            self.closed_only(button(tr("Remove everything…"), "danger", self.purge)),
        ], 4)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setRowStretch(5, 1)
        return page

    def _refresh_trouble(self) -> None:
        self.logging.blockSignals(True)
        self.logging.setChecked(bool(self.conf.faithlife_product_logging))
        self.logging.blockSignals(False)

    def run_health_checks(self) -> None:
        clear_layout(self.checks_box)
        self.checks_box.addWidget(label(tr("Checking…"), "muted"))

        def check() -> None:
            results: list[tuple[bool, str, str]] = []
            installed = self.is_installed()
            results.append((installed, tr("Logos is installed"),
                            self.conf.logos_exe or tr("Not installed yet")))
            if installed:
                self.logos.monitor()
                leftover = self.logos.logos_state == State.STOPPED and bool(wine.leftover_wine(self.conf.wine_prefix))
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
            except system.OpenGLIncompatible:
                results.append((False, tr("Graphics (OpenGL)"), tr("OpenGL 3.2 or newer is needed")))
            results.append((True, tr("Internet"), tr("Offline mode is on") if network.is_offline()
                            else tr("Online")))
            results.append((desktop_integrations.is_installed(), tr("Desktop integrations"),
                            tr("Installed") if desktop_integrations.is_installed() else tr("Not installed")))
            self.signals.health.emit(results)

        self.start_thread(check)

    def _show_health(self, results: list) -> None:
        clear_layout(self.checks_box)
        for ok, title, detail in results:
            left = pill(tr("OK") if ok else tr("Check"), "ok" if ok else "warn")
            left.setMinimumWidth(56)
            left.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right = None
            if not ok and title == tr("No Wine left running"):
                right = button(tr("End them"), None, self.end_leftover_wine)
            self.checks_box.addWidget(row(title, str(detail), right, left))

    def run_indexing(self) -> None:
        self.start_thread(self.logos.index)

    def end_leftover_wine(self) -> None:
        def run():
            wine.wineserver_kill(self)
            self.signals.recheck.emit()
        self.start_thread(run)

    def remove_library_catalog(self) -> None:
        self.start_thread(control.remove_library_catalog, self)

    def remove_indexes(self) -> None:
        self.start_thread(control.remove_all_index_files, app=self)

    def install_icu(self) -> None:
        self.start_thread(wine.enforce_icu_data_files, app=self)

    def install_deps(self) -> None:
        self.start_thread(utils.install_dependencies, self)

    def purge(self) -> None:
        def run():
            control.purge(self)
            self.clear_status()
            self.populate_defaults()
            self._refresh_later()
        self.start_thread(run)

    def run_backup(self) -> None:
        self.start_thread(backup.backup, app=self)

    def run_restore(self) -> None:
        self.start_thread(backup.restore, app=self)

    def get_support(self) -> None:
        self.start_thread(control.get_support, self)

    def open_logs(self) -> None:
        open_path(Path(self.conf.app_log_path).parent)

    def switch_logging(self) -> None:
        action = "enable" if self.logging.isChecked() else "disable"
        self.start_thread(self.logos.switch_logging, action=action)

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
            except (requests.RequestException, OSError) as error:
                self.status(tr("winetricks isn't available: {error}").format(error=error))
                return
            if not Path(binary).exists():
                self.status(tr("winetricks isn't available with this Wine build."))
                return
            system.offer_winetricks_tools(self)
            subprocess.Popen([binary], env=wine.get_wine_env(self), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.start_thread(run)

    def run_windows_program(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self.root, tr("Run a Windows program"), str(Path.home()),
            tr("Windows programs (*.exe *.msi);;All files (*)"))
        if filename:
            self.run_wine_tool(filename)
