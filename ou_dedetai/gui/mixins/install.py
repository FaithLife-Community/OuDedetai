"""Installing Logos from the window."""
from ... import constants, installer
from ..app import InstallerWindow, Toplevel
from ..blocks import INSTALLING, SIMPLE
from .base import WindowBase


class InstallMixin(WindowBase):
    """Installing Logos: the one-click install, Choose options and the guide."""

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
                # One-click install always uses the recommended Wine (the chosen channel's
                # newest build), not one left in the config by an earlier attempt.
                # "Choose options…" keeps a manual choice.
                self.conf.wine_binary = constants.WINE_RECOMMENDED_TARBALL_SIGIL
                installer.install(self)
            finally:  # errors are reported by start_thread
                self._installing = False
                self.signals.install_finished.emit()
        self.start_thread(install)

    def _install_finished(self) -> None:
        self._installing = False
        # Keep the "Install Complete!" message; the full bar isn't needed any more.
        self.status_gui.progress.setVisible(False)
        self.show_view(SIMPLE)
        self.refresh()
        # The check at start-up found nothing to check before the install, so the
        # Update menu would say "Checking for updates…" until the next start.
        if self.is_installed():
            self.start_thread(self._check_updates)

    def run_installer(self) -> None:
        dialog = Toplevel(self.root)
        window = InstallerWindow(dialog, self.root, self)
        # The options dialog closes itself and starts installer.install; show the guide too.
        window.gui.okay_button.clicked.connect(self._begin_guide)
        dialog.exec()

    def _begin_guide(self, *_) -> None:
        self._installing = True
        self.guide.set_product(self.conf.faithlife_product, self.conf.faithlife_product_icon_path)
        self.show_view(INSTALLING)
