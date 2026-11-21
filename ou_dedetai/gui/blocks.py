"""Small building blocks of the window: labels, pills, buttons, cards and rows."""
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .style import tr

# The window's views, and the full view's pages.
SIMPLE, INSTALLING, FULL = 0, 1, 2
HOME, SETTINGS, TROUBLE = 0, 1, 2


def product_name(product: str) -> str:
    """Faithlife's full product name, as shown beside its icon."""
    return "Logos Bible Software" if product == "Logos" else product


def label(text: str = "", role: Optional[str] = None, wrap: bool = True) -> QLabel:
    w = QLabel(text)
    w.setWordWrap(wrap)
    w.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        w.setProperty("role", role)
    return w


def pill(text: str, kind: str) -> QLabel:
    w = QLabel(text)
    w.setProperty("pill", kind)
    w.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return w


def set_pill(w: QLabel, text: str, kind: str) -> None:
    w.setText(text)
    w.setProperty("pill", kind)
    w.style().unpolish(w)
    w.style().polish(w)


def set_kind(w: QWidget, kind: Optional[str]) -> None:
    """Restyle a button, e.g. "available" (light blue) when it has an update to offer."""
    if w.property("kind") != kind:
        w.setProperty("kind", kind)
        w.style().unpolish(w)
        w.style().polish(w)


def button(text: str, kind: Optional[str] = None, slot: Optional[Callable] = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(lambda _=False: slot())
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def card(accent: Optional[str] = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    if accent:
        frame.setProperty("accent", accent)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(8)
    return frame, layout


def row(title: str, subtitle: str = "", right: Optional[QWidget] = None,
        left: Optional[QWidget] = None) -> QWidget:
    """A card row: optional left widget, bold title + muted subtitle, optional right widget."""
    w = QFrame()
    w.setObjectName("rowline")
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 8, 0, 4)
    h.setSpacing(12)
    if left is not None:
        h.addWidget(left, 0, Qt.AlignmentFlag.AlignTop)
    text = QVBoxLayout()
    text.setSpacing(1)
    t = label(title, "strong")
    text.addWidget(t)
    if subtitle:
        text.addWidget(label(subtitle, "muted"))
    h.addLayout(text, 1)
    if right is not None:
        h.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)
    return w


def scrolled(widget: QWidget, page: bool = True) -> QScrollArea:
    """A frameless scroll area around `widget`; a page gets the page background."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    if page:
        widget.setObjectName("od-page")
    area.setWidget(widget)
    return area


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            # Detach now: deleteLater alone leaves the old rows drawn under the new ones
            # until the event loop next runs.
            widget.setParent(None)
            widget.deleteLater()


def renderer_name(value: str) -> str:
    return {"dxvk": "DXVK", "gl": "OpenGL", "vulkan": "Vulkan", "gdi": "GDI",
            "default": tr("Wine default"), "unknown": tr("Unknown")}.get(value, value)


def open_path(path: str | Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
