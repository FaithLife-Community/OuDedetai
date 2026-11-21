"""Akousousin (Read Aloud voices and dictation)."""
from PySide6.QtWidgets import QWidget

from ... import network, system
from ..blocks import button, row, set_kind
from ..style import tr
from .base import WindowBase


class AkousousinMixin(WindowBase):
    """Akousousin: its row on Home, its update check, its button's state and its update."""

    def _akousousin_row(self) -> QWidget:
        self.p_speech = button(tr("Update"), None, self.update_akousousin)
        return row(tr("Akousousin"), tr("Read Aloud voices and dictation"), self.p_speech)

    def _check_akousousin_update(self, updates: dict) -> None:
        if system.akousousin_installed():
            newer = system.akousousin_update(self)
            updates["aks"] = (newer is not None, tr("Update Akousousin to {version}").format(version=newer)
                              if newer else tr("Akousousin is up to date"))

    def _show_akousousin(self) -> None:
        if not self.is_installed() or network.is_offline():
            self.p_speech.setEnabled(False)
            set_kind(self.p_speech, None)
            return
        if not system.akousousin_installed():
            set_kind(self.p_speech, None)
            self.p_speech.setText(tr("Install"))
            self.p_speech.setEnabled(not network.is_offline())
            return
        can, _ = self._updates.get("aks", (False, ""))
        self.p_speech.setText(tr("Update") if can else tr("Up to date"))
        self.p_speech.setEnabled(can and not self._logos_open())  # it registers itself in the prefix
        set_kind(self.p_speech, "available" if can else None)

    def update_akousousin(self) -> None:
        def run():
            system.update_akousousin(self)
            self._check_updates()
        self.start_thread(run)
