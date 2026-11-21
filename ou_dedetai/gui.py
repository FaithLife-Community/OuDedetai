from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)
from ou_dedetai.app import App

from .gui_style import tr


class ChoiceGui(QWidget):
    _default_prompt = "Choose…"

    def __init__(self, root, question: str, options: list[str], **kwargs):
        super().__init__(root)
        self.setContentsMargins(5, 5, 5, 5)
        layout = QGridLayout(self)

        self.question_label = QLabel(question)
        self.answer_dropdown = QComboBox()
        self.answer_dropdown.addItems(options)
        if options:
            self.answer_dropdown.setCurrentIndex(0)

        self.cancel_button = QPushButton(tr("Cancel"))
        self.okay_button = QPushButton(tr("Confirm"))

        layout.addWidget(self.question_label, 0, 0)
        layout.addWidget(self.answer_dropdown, 0, 1, 1, 2)
        layout.addWidget(self.cancel_button, 1, 1)
        layout.addWidget(self.okay_button, 1, 2)


class InfoGui(QWidget):
    _default_prompt = "Info"

    def __init__(self, root, message: str, **kwargs):
        super().__init__(root)
        self.setContentsMargins(5, 5, 5, 5)
        layout = QVBoxLayout(self)

        self.info_text = QPlainTextEdit(message)
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumWidth(350)

        self.okay_button = QPushButton(tr("OK"))
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.okay_button)

        layout.addWidget(self.info_text)
        layout.addLayout(button_layout)


class InstallerGui(QWidget):
    def __init__(self, root, app: App, **kwargs):
        super().__init__(root)
        self.app = app
        self.setContentsMargins(5, 5, 5, 5)
        layout = QGridLayout(self)

        self.product_label = QLabel(tr("Product:"))
        self.product_dropdown = QComboBox()
        self.product_dropdown.setEditable(False)
        self.product_dropdown.addItems(["Logos", "Verbum"])
        if app.conf._raw.faithlife_product:
            self.product_dropdown.setCurrentText(
                app.conf._raw.faithlife_product
            )

        self.release_label = QLabel(tr("Release:"))
        self.release_dropdown = QComboBox()
        self.release_dropdown.setEditable(False)
        if app.conf._raw.faithlife_product_release:
            self.release_dropdown.addItem(
                app.conf._raw.faithlife_product_release
            )

        self.wine_label = QLabel(tr("Wine:"))
        self.wine_dropdown = QComboBox()
        self.wine_dropdown.setEditable(False)
        if app.conf._raw.wine_binary:
            self.wine_dropdown.addItem(app.conf.wine_binary)

        self.skipdeps_label = QLabel(tr("Install system packages:"))
        self.skipdeps_checkbox = QCheckBox()
        self.skipdeps_checkbox.setChecked(
            not app.conf.skip_install_system_dependencies
        )

        self.cancel_button = QPushButton(tr("Cancel"))
        self.okay_button = QPushButton(tr("Install"))
        self.okay_button.setEnabled(False)

        widgets = [
            (self.product_label, self.product_dropdown),
            (self.release_label, self.release_dropdown),
            (self.wine_label, self.wine_dropdown),
            (self.skipdeps_label, self.skipdeps_checkbox),
        ]

        for row, (label, widget) in enumerate(widgets):
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 1, 1, 3)

        layout.addWidget(self.cancel_button, 5, 2)
        layout.addWidget(self.okay_button, 5, 3)


class StatusGui(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.message_label)
        layout.addWidget(self.progress)

    def set_status(self, message: str, percent: int | None = None):
        self.message_label.setText(message.strip())
        if percent is None:
            self.progress.setRange(0, 0)
            self.progress.setVisible(True)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)
            self.progress.setVisible(percent > 0)


class StatusWithLabelGui(StatusGui):
    def __init__(self, root, label: str, *args, **kwargs):
        super().__init__(root, **kwargs)

        self.app_label = QLabel(label)
        self.app_label.setProperty("role", "heading")

        self.layout().insertWidget(0, self.app_label)
        self.layout().insertWidget(
            1,
            QFrame(
                frameShape=QFrame.Shape.HLine
            ),
        )
