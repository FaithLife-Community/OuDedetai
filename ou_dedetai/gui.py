from PySide6 import QtWidgets
from ou_dedetai.app import App


class ChoiceGui(QtWidgets.QWidget):
    _default_prompt = "Choose…"

    def __init__(self, root, question: str, options: list[str], **kwargs):
        super().__init__(root)
        self.setContentsMargins(5, 5, 5, 5)
        layout = QtWidgets.QGridLayout(self)

        self.question_label = QtWidgets.QLabel(question)
        self.answer_dropdown = QtWidgets.QComboBox()
        self.answer_dropdown.addItems(options)
        if options:
            self.answer_dropdown.setCurrentIndex(0)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.okay_button = QtWidgets.QPushButton("Confirm")

        layout.addWidget(self.question_label, 0, 0)
        layout.addWidget(self.answer_dropdown, 0, 1, 1, 2)
        layout.addWidget(self.cancel_button, 1, 1)
        layout.addWidget(self.okay_button, 1, 2)


class InfoGui(QtWidgets.QWidget):
    _default_prompt = "Info"

    def __init__(self, root, message: str, **kwargs):
        super().__init__(root)
        self.setContentsMargins(5, 5, 5, 5)
        layout = QtWidgets.QVBoxLayout(self)

        self.info_text = QtWidgets.QPlainTextEdit(message)
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumWidth(350)

        self.okay_button = QtWidgets.QPushButton("Okay")
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.okay_button)

        layout.addWidget(self.info_text)
        layout.addLayout(button_layout)


class InstallerGui(QtWidgets.QWidget):
    def __init__(self, root, app: App, **kwargs):
        super().__init__(root)
        self.app = app
        self.setContentsMargins(5, 5, 5, 5)
        layout = QtWidgets.QGridLayout(self)

        self.product_label = QtWidgets.QLabel("Product & Version:")
        self.product_dropdown = QtWidgets.QComboBox()
        self.product_dropdown.setEditable(False)
        self.product_dropdown.addItems(["Logos", "Verbum"])
        if app.conf._raw.faithlife_product:
            self.product_dropdown.setCurrentText(
                app.conf._raw.faithlife_product
            )

        self.version_label = QtWidgets.QLabel("Version:")
        self.version_dropdown = QtWidgets.QComboBox()
        self.version_dropdown.setEditable(False)
        self.version_dropdown.setFixedWidth(65)
        # TODO: Remove this dropdown.
        self.version_dropdown.addItems(["10"])
        if app.conf._raw.faithlife_product_version:
            self.version_dropdown.setCurrentText(
                app.conf._raw.faithlife_product_version
            )

        self.release_label = QtWidgets.QLabel("Release:")
        self.release_dropdown = QtWidgets.QComboBox()
        self.release_dropdown.setEditable(False)
        if app.conf._raw.faithlife_product_release:
            self.release_dropdown.addItem(
                app.conf._raw.faithlife_product_release
            )

        self.wine_label = QtWidgets.QLabel("Wine exe:")
        self.wine_dropdown = QtWidgets.QComboBox()
        self.wine_dropdown.setEditable(False)
        if app.conf._raw.wine_binary:
            self.wine_dropdown.addItem(app.conf.wine_binary)

        self.skipdeps_label = QtWidgets.QLabel("Install Dependencies:")
        self.skipdeps_checkbox = QtWidgets.QCheckBox()
        self.skipdeps_checkbox.setChecked(
            not app.conf.skip_install_system_dependencies
        )

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.okay_button = QtWidgets.QPushButton("Install")
        self.okay_button.setEnabled(False)

        widgets = [
            (self.product_label, self.product_dropdown),
            (self.version_label, self.version_dropdown),
            (self.release_label, self.release_dropdown),
            (self.wine_label, self.wine_dropdown),
            (self.skipdeps_label, self.skipdeps_checkbox),
        ]

        for row, (label, widget) in enumerate(widgets):
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 1, 1, 3)

        layout.addWidget(self.cancel_button, 5, 2)
        layout.addWidget(self.okay_button, 5, 3)


class StatusGui(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.message_label = QtWidgets.QLabel()
        self.message_label.setWordWrap(True)
        self.progress = QtWidgets.QProgressBar()
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

        self.app_label = QtWidgets.QLabel(label)
        self.app_label.setStyleSheet("font-size: 16pt;")

        self.layout().insertWidget(0, self.app_label)
        self.layout().insertWidget(
            1,
            QtWidgets.QFrame(
                frameShape=QtWidgets.QFrame.Shape.HLine
            ),
        )
