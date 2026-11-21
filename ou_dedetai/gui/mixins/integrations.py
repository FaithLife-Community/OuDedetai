"""The desktop integrations and reading plans."""
from PySide6.QtWidgets import QFrame, QProgressBar, QVBoxLayout, QWidget

from ... import desktop_integrations, installer, network
from ..blocks import button, clear_layout, label, set_kind
from ..style import tr
from .base import WindowBase


class IntegrationsMixin(WindowBase):
    """The desktop integrations, app menu shortcuts and reading plans."""

    def _build_reading_card(self) -> QWidget:
        """Holder for the reading cards: a reading plan, then today's devotional."""
        box = QWidget()
        self.reading_cards = QVBoxLayout(box)
        self.reading_cards.setContentsMargins(0, 0, 0, 0)
        self.reading_cards.setSpacing(10)
        box.setVisible(False)
        return box

    def _plan_card(self, heading: str, plan: dict, progress: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reading")
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QFrame()
        head.setObjectName("readinghead")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(12, 8, 12, 8)
        t = label(heading, "strong")
        hv.addWidget(t)
        hv.addWidget(label(plan.get("title", ""), "muted"))
        v.addWidget(head)
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 8, 12, 10)
        bv.setSpacing(4)
        for reading in plan.get("readings", [])[:5]:
            bv.addWidget(button(reading.get("label") or reading.get("short") or "", "link",
                                lambda url=reading.get("url"): self.open_link(url)))
        if progress:
            if plan.get("status"):
                bv.addWidget(label(plan["status"], "muted"))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(round(100 * float(plan.get("progress") or 0))))
            bar.setTextVisible(False)
            bar.setMaximumHeight(6)
            bar.setAccessibleName(tr("Plan progress"))
            bv.addWidget(bar)
        v.addWidget(body)
        return frame

    def _render_reading(self) -> None:
        clear_layout(self.reading_cards)
        with_readings = [p for p in self._plans if p.get("readings")]
        plan = next((p for p in with_readings if p.get("kind") != "devotional"), None)
        devotional = next((p for p in with_readings if p.get("kind") == "devotional"), None)
        if plan:
            self.reading_cards.addWidget(self._plan_card(tr("Reading plan"), plan, progress=True))
        if devotional:
            self.reading_cards.addWidget(self._plan_card(tr("Today's devotional"), devotional, progress=False))
        if plan:
            self.reading_cards.addWidget(label(tr("Mark readings done in Logos."), "muted"))
        self.reading_card.setVisible(bool(plan or devotional))

    def _offer_integrations(self) -> None:
        """The one-time offer; if it installs them, show the reading plans and layouts now
        rather than after a restart."""
        before = desktop_integrations.is_installed()
        desktop_integrations.offer(self)
        if not before and desktop_integrations.is_installed():
            self._load_integrations()

    def _load_integrations(self) -> None:
        if not desktop_integrations.is_installed():
            return
        self.signals.integrations.emit(desktop_integrations.reading_plans(), desktop_integrations.saved_layouts())

    def _integrations_loaded(self, plans: list, layouts: list) -> None:
        self._plans, self._layouts = plans, layouts
        self._render_reading()

    def _show_desktop_integrations(self) -> None:
        offline = network.is_offline()
        if not desktop_integrations.is_installed():
            set_kind(self.p_desktop, None)
            self.p_desktop.setText(tr("Install"))
            self.p_desktop.setEnabled(not offline)
            return
        can, _ = self._updates.get("desktop", (False, ""))
        self.p_desktop.setText(tr("Update") if can else tr("Installed"))
        self.p_desktop.setEnabled(can and not offline)
        set_kind(self.p_desktop, "available" if can and not offline else None)

    def recreate_shortcuts(self) -> None:
        def run():
            installer.create_launcher_shortcuts(self)
            self.status(tr("App menu shortcuts and the Logos link handler recreated for this install."), 0)
        self.start_thread(run)

    def install_integrations(self) -> None:
        def run():
            if desktop_integrations.install(self) and "desktop" in self._updates:
                self._updates = {**self._updates, "desktop": (False, tr("Desktop integrations are up to date"))}
            self._load_integrations()
            self._refresh_later()
        self.start_thread(run)
