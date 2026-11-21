"""Updates from the window."""
import logging

import requests
from PySide6.QtWidgets import QMenu

from ... import constants, desktop_integrations, installer, network, utils
from ..blocks import set_kind
from ..style import tr
from .base import WindowBase


# An update check that fails this way (no network, an odd version string) just leaves
# that update out of the menu; anything else is a bug and is reported.
UPDATE_CHECK_ERRORS = (requests.RequestException, OSError, ValueError, TypeError)


class UpdatesMixin(WindowBase):
    """Update checks, the Update menu and button, and the updates themselves."""

    def _update_menu(self) -> QMenu:
        menu = QMenu()
        menu.aboutToShow.connect(lambda m=menu: self._fill_update_menu(m))
        return menu

    def _fill_update_menu(self, menu: QMenu) -> None:
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
                          ("logos", self.update_faithlife_product), ("aks", self.update_akousousin),
                          ("desktop", self.install_integrations)):
            enabled, text = self._updates.get(key, (False, ""))
            if text:
                wait = enabled and key in ("wine", "logos", "aks") and self._logos_open()
                a = menu.addAction(tr("{update} (close Logos first)").format(update=text) if wait else text)
                a.setEnabled(enabled and not wait)
                a.triggered.connect(slot)

    def _check_updates(self) -> dict:
        """Look for updates (background thread); the window shows them via the updates signal.
        Returns what was found, for callers that report it straight away."""
        if network.is_offline() or not self.is_installed():
            return {}
        updates: dict[str, tuple[bool, str]] = {}
        try:
            status, _ = utils.compare_recommended_wine_version(self)
            build = utils.recommended_wine_build_name(self) if status == 0 else None
            updates["wine"] = (status == 0,
                               tr("Update Wine to {build}").format(build=build) if build
                               else tr("Update Wine to the recommended build") if status == 0
                               else tr("Wine is up to date"))
        except UPDATE_CHECK_ERRORS:
            logging.debug("Wine update check failed", exc_info=True)
        try:
            result = utils.compare_logos_linux_installer_version(self)
            can = constants.RUNMODE == "binary" and result == utils.VersionComparison.OUT_OF_DATE
            updates["app"] = (can, tr("Update Ou Dedetai to {version}").format(version=self.conf.app_latest_version)
                              if can else tr("Ou Dedetai is up to date"))
        except UPDATE_CHECK_ERRORS:
            logging.debug("Ou Dedetai update check failed", exc_info=True)
        if self._oinos():
            updates["logos"] = (False, tr("Logos updates itself"))
        else:
            try:
                latest = self.conf.is_installed_faithlife_product_release_latest
                updates["logos"] = (not latest, tr("Update Logos") if not latest else tr("Logos is up to date"))
            except UPDATE_CHECK_ERRORS:
                logging.debug("Logos update check failed", exc_info=True)
        self._check_akousousin_update(updates)
        if desktop_integrations.is_installed() and desktop_integrations.desktop():
            newer = desktop_integrations.update_available(self)
            updates["desktop"] = (newer is not None,
                                  tr("Update the desktop integrations to {version}").format(version=newer)
                                  if newer else tr("Desktop integrations are up to date"))
        self.signals.updates.emit(updates)
        return updates

    def _updates_checked(self, updates: dict) -> None:
        self._updates = updates
        self._show_akousousin()
        self._show_desktop_integrations()
        self._show_update_button()

    def _show_update_button(self) -> None:
        """Light blue, with a count and the list as a tooltip, when something can be updated."""
        available = [text for can, text in self._updates.values() if can] if not network.is_offline() else []
        for b in (self.s_update, self.h_update):
            b.setText(tr("Update ({count})").format(count=len(available)) if available else tr("Update"))
            b.setToolTip("\n".join(available))
            set_kind(b, "available" if available else None)

    def check_updates_now(self) -> None:
        """Ou Dedetai, Wine, Logos and Akousousin, ignoring the half-day cache."""
        if network.is_offline():
            self.status(tr("Offline mode is on, so Ou Dedetai won't check for updates."), 0)
            return

        def run():
            self.status(tr("Checking for updates…"))
            self.conf._network.clear_cache()
            available = [text for can, text in self._check_updates().values() if can]
            self.status(tr("Updates available: {names}").format(names="; ".join(available)) if available
                        else tr("Everything is up to date."), 0)
        self.start_thread(run)

    def update_wine_config(self) -> None:
        def run():
            installer.update_wine_config(self)
            self.signals.settings_changed.emit()
        self.start_thread(run)

    def update_faithlife_product(self) -> None:
        def run():
            utils.update_faithlife_product(app=self)
            self._check_updates()
        self.start_thread(run)

    def update_to_latest_lli_release(self) -> None:
        self.start_thread(utils.update_to_latest_lli_release, app=self)

    def update_wine(self) -> None:
        def run():
            installer.update_to_latest_wine(self)
            self._check_updates()  # so the Update button stops highlighting it
        self.start_thread(run)
