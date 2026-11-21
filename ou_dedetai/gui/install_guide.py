"""The guide shown while installing: each step in plain words."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import wine_settings
from . import style
from .blocks import card, label, pill, product_name, scrolled, set_pill
from .style import tr

# Status messages from installer.py, in order, matched by their start, with plain words.
INSTALL_STEPS: list[tuple[tuple[str, ...], str, str]] = [
    (("Asking questions", "Install is running", "Ensuring installation directories"),
     "Preparing", "Choosing where Logos goes"),
    (("Ensuring system dependencies", "Checking available OpenGL"),
     "Checking your computer", "Folders and graphics; nothing is installed system-wide"),
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


class InstallGuide(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("od-page")
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 22, 32, 22)
        v.setSpacing(12)
        head = QHBoxLayout()
        self.icon = QLabel()
        head.addWidget(self.icon)
        titles = QVBoxLayout()
        self.title = label(tr("Installing Logos"), "title")
        self.subtitle = label(tr("You can use your computer meanwhile."), "muted")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        v.addLayout(head)

        frame, steps = card()
        steps.addWidget(label(tr("What's happening"), "h2"))
        self.rows: list[tuple[QLabel, QLabel, QLabel]] = []
        self.row_widgets: list[QWidget] = []
        for i, (_, title, detail) in enumerate(INSTALL_STEPS):
            mark = pill(str(i + 1), "off")
            mark.setMinimumWidth(26)
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 4, 0, 4)
            h.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(1)
            t = label(tr(title), "strong")
            d = label(tr(detail) if detail else "", "muted")
            d.setVisible(bool(detail))
            col.addWidget(t)
            col.addWidget(d)
            h.addLayout(col, 1)
            steps.addWidget(w)
            self.rows.append((mark, t, d))
            self.row_widgets.append(w)
        settings_detail = self.rows[6][2]
        settings_detail.setText(", ".join(
            tr(s.title) for s in wine_settings.SETTINGS if s.group == wine_settings.Group.NEEDED))
        settings_detail.setVisible(True)
        self.area = scrolled(frame, page=False)
        v.addWidget(self.area, 1)
        self.current = -1

    def set_product(self, product: str, icon_path) -> None:
        self.title.setText(tr("Installing {product}").format(product=product_name(product)))
        self.icon.setPixmap(style.pixmap(icon_path, 44))

    def update_status(self, message: str) -> None:
        """Tick off the steps; the window's own status bar shows the message and progress."""
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
