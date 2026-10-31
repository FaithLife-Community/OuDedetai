from PySide6 import QtWidgets
from ou_dedetai.app import App
from . import constants


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


class ControlGui(StatusGui):
    def __init__(self, root, *args, **kwargs):
        super().__init__(root, **kwargs)
        layout = QtWidgets.QGridLayout()
        self.layout().addLayout(layout)

        # Run/install app.
        self.app_label = QtWidgets.QLabel("FaithLife app")
        self.app_button = QtWidgets.QPushButton("Install")
        self.app_install_advanced = QtWidgets.QPushButton(
            "Advanced Install"
        )

        layout.addWidget(self.app_label, 0, 0)
        layout.addWidget(self.app_button, 0, 1)
        layout.addWidget(self.app_install_advanced, 0, 2)

        # Installed app actions.
        layout.addWidget(self._separator(), 1, 0, 1, 3)

        self.actions_label = QtWidgets.QLabel("App actions:")
        self.actions_group = QtWidgets.QButtonGroup(self)
        self.actions_group.setExclusive(True)

        self.run_indexing_radio = self._radio(
            "Run indexing", "run-indexing"
        )
        self.remove_library_catalog_radio = self._radio(
            "Remove library catalog", "remove-library-catalog"
        )
        self.remove_index_files_radio = self._radio(
            "Remove all index files", "remove-index-files"
        )
        self.uninstall_radio = self._radio(
            "Uninstall", "uninstall"
        )
        self.install_icu_radio = self._radio(
            "Install/Update ICU files", "install-icu"
        )

        self.actions_button = QtWidgets.QPushButton("Run action")
        self.actions_button.setEnabled(False)

        layout.addWidget(self.actions_label, 2, 0)
        layout.addWidget(self.run_indexing_radio, 2, 1, 1, 2)
        layout.addWidget(self.remove_library_catalog_radio, 3, 1, 1, 2)
        layout.addWidget(self.actions_button, 4, 0)
        layout.addWidget(self.remove_index_files_radio, 4, 1, 1, 2)
        layout.addWidget(self.uninstall_radio, 5, 1, 1, 2)
        layout.addWidget(self.install_icu_radio, 6, 1, 1, 2)

        layout.addWidget(self._separator(), 7, 0, 1, 3)

        # Configuration and dependencies.
        self.config_label = QtWidgets.QLabel("Edit config file")
        self.config_button = QtWidgets.QPushButton("Edit …")
        self.deps_label = QtWidgets.QLabel("Install dependencies")
        self.deps_button = QtWidgets.QPushButton("Install")

        layout.addWidget(self.config_label, 8, 0)
        layout.addWidget(self.config_button, 8, 1)
        layout.addWidget(self.deps_label, 9, 0)
        layout.addWidget(self.deps_button, 9, 1)

        # Faithlife product update.
        self.update_product_label = QtWidgets.QLabel(
            "Update Faithlife Product"
        )
        self.update_product_button = QtWidgets.QPushButton("Update")

        layout.addWidget(self.update_product_label, 10, 0)
        layout.addWidget(self.update_product_button, 10, 1)

        # Backup and restore. Retained but not currently displayed.
        self.backups_label = QtWidgets.QLabel("Backup/restore data")
        self.backup_button = QtWidgets.QPushButton("Backup")
        self.restore_button = QtWidgets.QPushButton("Restore")

        # Installer update.
        self.update_lli_label = QtWidgets.QLabel(
            f"Update {constants.APP_NAME}\n\n"
        )
        self.update_lli_button = QtWidgets.QPushButton("Update")

        layout.addWidget(self.update_lli_label, 11, 0)
        layout.addWidget(self.update_lli_button, 11, 1)

        # AppImage controls.
        self.latest_appimage_label = QtWidgets.QLabel(
            "Update to Latest AppImage"
        )
        self.latest_appimage_button = QtWidgets.QPushButton("Run")
        self.set_appimage_label = QtWidgets.QLabel("Set AppImage")
        self.set_appimage_button = QtWidgets.QPushButton("Run")

        layout.addWidget(self.latest_appimage_label, 12, 0)
        layout.addWidget(self.latest_appimage_button, 12, 1)
        layout.addWidget(self.set_appimage_label, 13, 0)
        layout.addWidget(self.set_appimage_button, 13, 1)

        # App logging.
        self.logging_label = QtWidgets.QLabel("Toggle app logging")
        self.logging_button = QtWidgets.QPushButton("Enable")

        layout.addWidget(self.logging_label, 14, 0)
        layout.addWidget(self.logging_button, 14, 1)

        # Support.
        self.support_label = QtWidgets.QLabel("Troubleshooting")
        self.support_button = QtWidgets.QPushButton("Get Support")

        layout.addWidget(self.support_label, 15, 0)
        layout.addWidget(self.support_button, 15, 1)

        layout.addWidget(self._separator(), 16, 0, 1, 3)

        # Status widgets are inherited from StatusGui.
        layout.addWidget(self.message_label, 17, 0, 1, 3)
        layout.addWidget(self.progress, 18, 0, 1, 3)

        layout.setColumnStretch(1, 1)

    def _separator(self):
        return QtWidgets.QFrame(
            self,
            frameShape=QtWidgets.QFrame.Shape.HLine,
        )

    def _radio(self, label, action):
        button = QtWidgets.QRadioButton(label)
        button.setProperty("action", action)
        self.actions_group.addButton(button)
        return button

    def show_advanced_install_button(self):
        self.app_install_advanced.show()


class ToolTip:
    """Qt provides native tooltips; retain the old helper interface."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.widget.setToolTip(text)

    def show_tooltip(self, event=None):
        self.widget.setToolTip(self.text)

    def hide_tooltip(self, event=None):
        pass


class PromptGui(QtWidgets.QWidget):
    def __init__(self, root, title="", prompt="", **kwargs):
        super().__init__(root)
        self.options = {"title": title, "prompt": prompt}
        self.root = root

    def draw_prompt(self):
        store_button = QtWidgets.QPushButton("Store Password", self.root)
        store_button.clicked.connect(
            lambda: input_prompt(
                self.root,
                self.options["title"],
                self.options["prompt"],
            )
        )
        store_button.show()


def show_error(
    message,
    fatal=True,
    detail=None,
    app=None,
    parent=None,
):
    title = "Fatal Error" if fatal else "Error"
    box = QtWidgets.QMessageBox(
        QtWidgets.QMessageBox.Icon.Critical,
        title,
        message,
        parent=parent if isinstance(parent, QtWidgets.QWidget) else None,
    )
    if detail:
        box.setInformativeText(detail)
    box.exec()

    if fatal and hasattr(app, "root"):
        app.root.close()


def ask_question(question, secondary, parent=None):
    result = QtWidgets.QMessageBox.question(
        parent,
        question,
        secondary,
        QtWidgets.QMessageBox.StandardButton.Yes
        | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No,
    )
    return (
        "yes"
        if result == QtWidgets.QMessageBox.StandardButton.Yes
        else "no"
    )


def input_prompt(root, title, prompt):
    text, accepted = QtWidgets.QInputDialog.getText(
        root,
        title,
        prompt,
        QtWidgets.QLineEdit.EchoMode.Password,
    )
    return text if accepted else None
