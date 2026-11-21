"""Choosing the Wine build."""
import logging
import os
from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMenu, QPushButton

from ... import installer, network, utils, wine, wine_settings
from ...logos import State
from ..blocks import button
from ..style import tr
from .base import WindowBase
from .updates import UPDATE_CHECK_ERRORS


class WineBuildsMixin(WindowBase):
    """Which Wine build Logos runs on: releases, test builds and AppImages."""

    def _oinos(self) -> bool:
        release = wine_settings.wine_release(self)
        return bool(release and wine.wine_supports_logos_updates(release))

    def _wine_label(self) -> str:
        release = wine_settings.wine_release(self)
        if release is None:
            return "–"
        text = f"{release.major}.{release.minor}"
        return f"{text} (oinos)" if wine.wine_supports_logos_updates(release) else text

    def _wine_build_button(self) -> QPushButton:
        """Choose a Wine build: our newest prerelease or release bundle, or a file."""
        b = button(tr("Choose a Wine build…"), None, lambda: None)
        menu = QMenu(b)
        self.wine_build_actions: dict[str, QAction] = {}
        for channel, text in (("dev", tr("Newest prerelease")), ("stable", tr("Newest release"))):
            action = menu.addAction(text)
            action.setData(text)
            action.triggered.connect(lambda _=False, c=channel: self.use_wine_release(c))
            self.wine_build_actions[channel] = action
        menu.addSeparator()
        menu.addAction(tr("A file on this computer (AppImage or tarball)…")).triggered.connect(self.set_appimage)
        menu.aboutToShow.connect(self._wine_build_menu_shown)
        b.setMenu(menu)
        return b

    def _wine_build_menu_shown(self) -> None:
        offline = network.is_offline()
        for action in self.wine_build_actions.values():
            action.setEnabled(not offline)
        if not offline and not self._wine_builds_known:
            self.start_thread(self._find_wine_builds)

    def _find_wine_builds(self) -> None:
        names = {}
        for channel in self.wine_build_actions:
            try:
                release = self.conf._network.wine_tarball_release(channel)
                names[channel] = (release.version, utils.wine_build_name(os.path.basename(release.download_url)))
            except UPDATE_CHECK_ERRORS:
                logging.debug(f"Couldn't look up the {channel} Wine build", exc_info=True)
        self.signals.wine_builds.emit(names)

    def _show_wine_builds(self, names: dict) -> None:
        self._wine_builds_known = bool(names)
        installed = utils.installed_wine_build_name(self) or ""
        for channel, action in self.wine_build_actions.items():
            text = action.data()
            if channel in names:
                name, build = names[channel]
                text = f"{text}: {name}" + (tr(" (in use)") if build == installed else "")
            action.setText(text)

    def use_wine_release(self, channel: str) -> None:
        if self.logos.logos_state in (State.RUNNING, State.STARTING):
            self.status(tr("Close Logos before changing its Wine."), 0)
            return
        if not self.approve(tr("Switch Wine?"), tr(
                "Ou Dedetai downloads this Wine build and uses it from now on. Wine updates will "
                "then follow the same kind of build (prereleases or releases).")):
            return

        def run():
            installer.use_wine_release(self, channel)
            self.status(tr("Wine switched."), 0)
            self._wine_builds_known = False  # "(in use)" moves
            self.signals.refresh.emit()
            self._check_updates()
        self.start_thread(run)

    def set_appimage(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self.root, tr("Choose a Wine build"), str(Path.home()),
            tr("Wine runner (*.AppImage *.tar.xz *.tar.gz *.tgz);;All files (*)"))
        if not filename:
            return
        if self.logos.logos_state in (State.RUNNING, State.STARTING):
            self.status(tr("Close Logos before changing its Wine."), 0)
            return

        def run():
            # No percentage: the bar animates until the switch is done (copying a big
            # AppImage takes a while and says nothing else meanwhile).
            self.status(tr("Setting up {name}…").format(name=Path(filename).name))
            installer.use_wine_file(self, filename)
            self._wine_builds_known = False  # "(in use)" moves
            self.signals.refresh.emit()
            self._check_updates()
        self.start_thread(run)
