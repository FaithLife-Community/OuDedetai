"""Look of the Qt windows: Faithlife's palette and type, native window frames.

Colours follow Faithlife's own MIT-licensed UI library (Faithlife/styled-ui,
theme/core.js), darkened where needed so text passes WCAG contrast (4.5:1).
"""
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPixmap

from .. import constants

# Translation context of every window string: tr() marks text for translation.
CONTEXT = "OuDedetai"


def tr(text: str) -> str:
    """Translate a window string into the desktop's language, if we have it."""
    return QCoreApplication.translate(CONTEXT, text)

BLUE = "#0174b9"          # buttons, links (styled-ui blue5; 5:1 with white)
BLUE_DARK = "#015d95"     # hover/pressed
BLUE_ACCENT = "#1e91d6"   # stripes, progress (styled-ui blue4; decoration only)
BLUE_LIGHT = "#d5ecfc"
BLUE_LIGHTEST = "#ebf7ff"
TEXT = "#3d3d3d"
TEXT_MUTED = "#575251"     # Faithlife grey
BORDER = "#dbdbdb"
BORDER_STRONG = "#c7c7c7"
PAGE = "#f5f5f5"
PANEL = "#ebebeb"
GREEN_BG, GREEN = "#e9f8e1", "#2f7a12"
YELLOW_BG, YELLOW = "#fff8e0", "#8a6400"
RED = "#bd2929"

# A white tick for checked boxes (drawn on our blue).
CHECK_MARK = (constants.APP_IMAGE_DIR / "check.svg").as_posix()

FONT_FAMILIES = ["Source Sans 3", "Source Sans Pro", "Noto Sans", "Cantarell", "DejaVu Sans"]

STYLESHEET = f"""
QWidget#od-root, QWidget#od-page {{ background: {PAGE}; color: {TEXT}; }}
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel[role="muted"] {{ color: {TEXT_MUTED}; }}
QLabel[role="title"] {{ font-size: 20pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 13pt; font-weight: 600; }}
QLabel[role="group"] {{ color: {TEXT_MUTED}; font-size: 9pt; font-weight: 700; }}
QLabel[role="heading"] {{ font-size: 16pt; }}
QLabel[role="strong"] {{ font-weight: 600; }}
QLabel[role="brand"] {{ font-size: 13pt; font-weight: 700; }}
QLabel[role="value"] {{ font-size: 13pt; font-weight: 600; }}
QFrame#card {{ background: white; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame#card[accent="true"] {{ border-top: 3px solid {BLUE_ACCENT}; }}
QFrame#card[accent="warn"] {{ border-top: 3px solid #e97732; }}
QFrame#sidebar {{ background: white; border-right: 1px solid {BORDER}; }}
QFrame#reading {{ background: white; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame#readinghead {{ background: {BLUE_LIGHTEST}; border-bottom: 1px solid {BLUE_LIGHT};
    border-top-left-radius: 6px; border-top-right-radius: 6px; }}
QFrame#rowline {{ border-top: 1px solid {PANEL}; }}
QPushButton, QToolButton {{
    background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: 3px; padding: 6px 14px; font-weight: 600;
}}
QPushButton:hover, QToolButton:hover {{ background: {BORDER}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #7a7a7a; background: {PAGE}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {BLUE_ACCENT}; }}
QPushButton[kind="primary"], QToolButton[kind="primary"] {{
    background: {BLUE}; border-color: {BLUE}; color: white;
}}
QPushButton[kind="primary"]:hover, QToolButton[kind="primary"]:hover {{ background: {BLUE_DARK}; }}
QPushButton[kind="primary"]:disabled, QToolButton[kind="primary"]:disabled {{
    background: {PANEL}; border-color: {BORDER_STRONG}; color: #6b6b6b; }}
QPushButton[kind="available"], QToolButton[kind="available"] {{
    background: {BLUE_LIGHTEST}; border-color: {BLUE}; color: {BLUE_DARK}; font-weight: 600; }}
QPushButton[kind="available"]:hover, QToolButton[kind="available"]:hover {{ background: {BLUE_LIGHT}; }}
QPushButton[kind="danger"] {{ background: white; color: {RED}; border-color: #e3b4ae; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {BLUE}; padding: 2px 0;
    font-weight: 400; text-align: left; }}
QPushButton[kind="link"]:hover {{ color: {BLUE_DARK}; text-decoration: underline; }}
QPushButton[kind="nav"] {{ background: transparent; border: none; text-align: left; padding: 8px 12px;
    font-weight: 400; font-size: 11pt; }}
QPushButton[kind="nav"]:checked {{ background: {BLUE_LIGHT}; color: {BLUE_DARK}; font-weight: 600; }}
QToolButton[kind="primary"]::menu-button {{ border-left: 1px solid #5aa8dc; width: 22px; }}
QToolButton[kind="primary"] {{ padding-right: 38px; }}  /* room for the arrow after "Run Logos" */
QLabel[pill="ok"] {{ background: {GREEN_BG}; color: {GREEN}; border-radius: 3px; padding: 1px 8px;
    font-weight: 600; font-size: 9pt; }}
QLabel[pill="warn"] {{ background: {YELLOW_BG}; color: {YELLOW}; border-radius: 3px; padding: 1px 8px;
    font-weight: 600; font-size: 9pt; }}
QLabel[pill="off"] {{ background: {PANEL}; color: {TEXT_MUTED}; border-radius: 3px; padding: 1px 8px;
    font-weight: 600; font-size: 9pt; }}
QProgressBar {{ background: {PANEL}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {BLUE_ACCENT}; border-radius: 4px; }}
QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 8px; }}
QCheckBox[role="strong"] {{ font-weight: 600; font-size: 11pt; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid #6b6b6b; border-radius: 3px;
    background: white; }}
QCheckBox::indicator:hover {{ border-color: {BLUE}; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border-color: {BLUE};
    image: url("{CHECK_MARK}"); }}
QCheckBox::indicator:disabled {{ border-color: {BORDER_STRONG}; background: {PAGE}; }}
QComboBox, QLineEdit {{ background: white; border: 1px solid {BORDER_STRONG}; border-radius: 3px;
    padding: 4px 8px; color: {TEXT}; }}
QMenu {{ background: white; border: 1px solid {BORDER_STRONG}; padding: 4px 0; }}
QMenu::item {{ padding: 6px 22px 6px 14px; color: {TEXT}; }}
QMenu::item:selected {{ background: {BLUE_LIGHTEST}; }}
QMenu::item:disabled {{ color: #7a7a7a; }}
QMenu::separator {{ height: 1px; background: {PANEL}; margin: 4px 0; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{ background: white; color: {TEXT}; border: 1px solid {BORDER_STRONG}; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(10)
    app.setFont(font)
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PAGE))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor("white"))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(BLUE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.Link, QColor(BLUE))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


def app_icon() -> QIcon:
    return QIcon(str(constants.APP_IMAGE_DIR / "icon.png"))


def pixmap(path, size: int) -> QPixmap:
    pm = QPixmap(str(path))
    if pm.isNull():
        return pm
    return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
