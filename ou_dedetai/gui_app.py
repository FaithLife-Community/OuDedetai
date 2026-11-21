import logging
import shutil
import threading
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QVBoxLayout,
)
from PySide6.QtCore import QEvent, QObject, Qt, QThread, Signal, Slot

from ou_dedetai.app import App
from ou_dedetai.config import EphemeralConfiguration
from ou_dedetai.constants import PROMPT_OPTION_DIRECTORY, PROMPT_OPTION_FILE, PROMPT_OPTION_NEW_FILE

from . import constants, gui, gui_style, installer, system, utils
from .gui_style import tr


class GuiBridge(QObject):
    invoke = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _run(self, request):
        callback, event, result = request
        try:
            result["value"] = callback()
        except Exception as exc:
            result["error"] = exc
        finally:
            event.set()


class Root(QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.classname = kwargs.get("className", constants.BINARY_NAME)
        self.icon = constants.APP_IMAGE_DIR / "icon.png"
        self.setWindowIcon(gui_style.app_icon())

    def set_content(self, widget):
        self.setCentralWidget(widget)


class Toplevel(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowIcon(gui_style.app_icon())


class GuiApp(App):
    """Implements the App interface for the GUI."""

    _exit_option: Optional[str] = None

    def __init__(self, root: Root, status_gui: gui.StatusGui, ephemeral_config: EphemeralConfiguration, **kwargs):
        super().__init__(ephemeral_config)
        self.root = root
        self._status_gui = status_gui
        self._bridge = GuiBridge(root)
        self.start_thread(self.populate_defaults)

    def _is_gui_thread(self):
        return QThread.currentThread() == self.root.thread()

    def _dispatch(self, callback, wait=True):
        """Execute a callback on the GUI thread."""
        if self._is_gui_thread():
            return callback()

        event = Event()
        result = {}
        self._bridge.invoke.emit((callback, event, result))

        if not wait:
            return None

        event.wait()
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _ask(self, question: str, options: list[str] | str) -> Optional[str]:
        if isinstance(options, list):
            answer = self._dispatch(
                lambda: ChoicePopUp(question, options, self.root).get_answer()
            )
        else:
            answer = options

        if answer == PROMPT_OPTION_DIRECTORY:
            return self._dispatch(
                lambda: self._select_directory(question)
            )
        if answer == PROMPT_OPTION_FILE:
            return self._dispatch(
                lambda: self._select_file(question)
            )
        if answer == PROMPT_OPTION_NEW_FILE:
            return self._dispatch(
                lambda: self._save_file(question)
            )
        return answer

    def _select_directory(self, question):
        result = QFileDialog.getExistingDirectory(
            self.root, question, str(Path.home())
        )
        return result or None

    def _select_file(self, question):
        result, _ = QFileDialog.getOpenFileName(
            self.root, question, str(Path.home())
        )
        return result or None

    def _save_file(self, question):
        result, _ = QFileDialog.getSaveFileName(
            self.root, question, str(Path.home())
        )
        return result or None

    def _info(self, message):
        self._dispatch(lambda: InfoPopUp(message, self.root).exec())

    def _pop_up(self, title, message):
        self._dispatch(
            lambda: QMessageBox.information(
                self.root, title, message
            )
        )

    def _status(self, message, percent=None):
        self._status_gui.set_status(message, percent)

    def clear_status(self):
        self._status_gui.set_status('', 0)

    def agree_to_licence(self, product: str, text: Optional[str]) -> bool:
        if not text:
            return super().agree_to_licence(product, text)

        def ask() -> bool:
            dialog = QDialog(self.root)
            dialog.setWindowTitle(tr("{product} licence agreement").format(product=product))
            dialog.resize(640, 560)
            layout = QVBoxLayout(dialog)
            intro = QLabel(tr("Please read {product}'s licence agreement. Installing needs you to "
                                        "accept it.").format(product=product))
            intro.setWordWrap(True)
            layout.addWidget(intro)
            body = QPlainTextEdit(text)
            body.setReadOnly(True)
            body.setAccessibleName(tr("Licence agreement"))
            layout.addWidget(body, 1)
            buttons = QDialogButtonBox()
            agree = buttons.addButton(tr("I agree"), QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
            agree.setProperty("kind", "primary")
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            return dialog.exec() == QDialog.DialogCode.Accepted
        return bool(self._dispatch(ask))

    def approve(self, question: str, context: str | None = None) -> bool:
        message = f"{question}\n\n{context or ''}".strip()
        return bool(self._dispatch(
            lambda: QMessageBox.question(
                self.root,
                question,
                message,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
        ))

    def _schedule_exit_on_main_thread(self, reason: str, intended: bool):
        self._dispatch(lambda: self.exit(reason, intended), wait=False)

    def _exit(self, reason: str, intended: bool = False):
        if not intended:
            self._dispatch(
                lambda: QMessageBox.critical(
                    self.root,
                    tr("Error"),
                    f"{reason}\n\n{constants.SUPPORT_MESSAGE}",
                )
            )
        self._dispatch(self.root.close, wait=False)

    @property
    def superuser_command(self) -> str:
        if shutil.which("pkexec"):
            return "pkexec"
        raise system.SuperuserCommandNotFound(
            "No superuser command found. Please install pkexec."
        )

    def populate_defaults(self):
        """Populate unset configuration values with GUI defaults."""
        if self.conf._raw.faithlife_product is None:
            self.conf.faithlife_product = constants.FAITHLIFE_PRODUCTS[0]

        if self.conf._raw.faithlife_product_version is None:
            self.conf.faithlife_product_version = (
                constants.FAITHLIFE_PRODUCT_VERSIONS[0]
            )

        if self.conf._network._faithlife_product_releases(
            self.conf._raw.faithlife_product,
            self.conf._raw.faithlife_product_version,
            self.conf._raw.faithlife_product_release_channel,
        ):
            if self.conf._raw.faithlife_product_release is None:
                self.conf.faithlife_product_release = (
                    self.conf.faithlife_product_releases[0]
                )
        else:
            def populate_release():
                releases = self.conf.faithlife_product_releases
                if releases and self.conf._raw.faithlife_product_release is None:
                    self.conf.faithlife_product_release = releases[0]

            self.start_thread(populate_release)

        if self.conf._raw.install_dir is None:
            self.conf.install_dir = self.conf.install_dir_default

        if self.conf._raw.wine_binary is None:
            wine_choices = utils.get_wine_options(self)
            if wine_choices:
                self.conf.wine_binary = wine_choices[0]


class ChoicePopUp(Toplevel):
    def __init__(self, question, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Question"))
        self.answer = None

        self.gui = gui.ChoiceGui(self, question, options)
        layout = QVBoxLayout(self)
        layout.addWidget(self.gui)

        self.gui.cancel_button.clicked.connect(self.reject)
        self.gui.okay_button.clicked.connect(self.confirm)

        self.gui.answer_dropdown.setEditable(False)
        self.gui.answer_dropdown.setCurrentIndex(0 if options else -1)

        self.resize(self.sizeHint())

    def confirm(self):
        answer = self.gui.answer_dropdown.currentText()
        if answer and answer != gui.ChoiceGui._default_prompt:
            self.answer = answer
            self.accept()

    def get_answer(self):
        self.exec()
        return self.answer

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self.confirm()
            return
        super().keyPressEvent(event)


class InfoPopUp(Toplevel):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Information"))

        self.gui = gui.InfoGui(self, message)
        layout = QVBoxLayout(self)
        layout.addWidget(self.gui)

        self.gui.okay_button.clicked.connect(self.accept)
        self.resize(self.sizeHint())

    def keyPressEvent(self, event):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Escape,
        ):
            self.accept()
            return
        super().keyPressEvent(event)


class InstallerWindow(QObject):
    def __init__(self, new_win, root: Root, app: GuiApp, **kwargs):
        super().__init__(new_win)
        self.win = new_win
        self.root = root
        self.app = app
        self.conf = app.conf
        self.start_thread = app.start_thread
        self.gui = gui.InstallerGui(self.win, app)
        self.installer_step = 0
        self.installer_step_count = 0

        self.win.setWindowTitle(f"{constants.APP_NAME} Installer")
        self.win.setModal(True)
        self.win.setWindowFlags(
            self.win.windowFlags()
            & ~Qt.WindowType.WindowMaximizeButtonHint
        )

        layout = QVBoxLayout(self.win)
        layout.addWidget(self.gui)

        self.gui.product_dropdown.currentTextChanged.connect(self.set_product)
        self.gui.release_dropdown.currentTextChanged.connect(self.set_release)
        self.gui.wine_dropdown.currentTextChanged.connect(self.set_wine)
        self.gui.skipdeps_checkbox.toggled.connect(self.set_skip_dependencies)
        self.gui.cancel_button.clicked.connect(self.on_cancel_released)
        self.gui.okay_button.clicked.connect(self.on_okay_released)

        self.app.config_updated_hooks.append(self._config_updated_hook)
        self._config_updated_hook()

        self.win.installEventFilter(self)
        self.win.resize(self.win.sizeHint())

    def eventFilter(self, watched, event):
        if watched is self.win and event.type() == QEvent.Type.KeyPress:
            if event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            ):
                self.on_okay_released()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.on_cancel_released()
                return True
        return super().eventFilter(watched, event)

    def _config_updated_hook(self):
        self.app._dispatch(self._update_config_gui, wait=False)

    def _update_config_gui(self):
        self.gui.product_dropdown.blockSignals(True)
        self.gui.release_dropdown.blockSignals(True)
        self.gui.wine_dropdown.blockSignals(True)
        self.gui.skipdeps_checkbox.blockSignals(True)

        self.gui.product_dropdown.setCurrentText(
            self.conf.faithlife_product or ""
        )

        self.gui.release_dropdown.clear()
        self.gui.release_dropdown.addItems(
            self.conf.faithlife_product_releases
        )
        self.gui.release_dropdown.setCurrentText(
            self.conf.faithlife_product_release or ""
        )

        wine_choices = utils.get_wine_options(self.app)
        self.gui.wine_dropdown.clear()
        self.gui.wine_dropdown.addItems(wine_choices)
        self.gui.wine_dropdown.setCurrentText(
            self.conf._raw.wine_binary or ""
        )

        self.gui.skipdeps_checkbox.setChecked(
            not self.conf.skip_install_system_dependencies
        )

        self.gui.product_dropdown.blockSignals(False)
        self.gui.release_dropdown.blockSignals(False)
        self.gui.wine_dropdown.blockSignals(False)
        self.gui.skipdeps_checkbox.blockSignals(False)

        self.set_input_widgets_state("enabled", [self.gui.okay_button])

    def _post_dropdown_change(self):
        self.installer_step = 0
        self.installer_step_count = 0
        self.conf.install_dir = self.conf.install_dir_default

    def set_input_widgets_state(self, state, widgets="all"):
        enabled = state == "enabled"
        all_widgets = [
            self.gui.product_dropdown,
            self.gui.release_dropdown,
            self.gui.wine_dropdown,
            self.gui.okay_button,
        ]
        if widgets == "all":
            widgets = all_widgets
        for widget in widgets:
            widget.setEnabled(enabled)

    def set_product(self, value):
        if value:
            self.conf.faithlife_product = value
            self._post_dropdown_change()

    def set_release(self, value):
        if value:
            self.conf.faithlife_product_release = value
            self._post_dropdown_change()

    def set_wine(self, value):
        if value:
            self.conf.wine_binary = value
            self._post_dropdown_change()

    def set_skip_dependencies(self, checked):
        self.conf.skip_install_system_dependencies = not checked
        logging.debug(
            f"> {self.conf.skip_install_system_dependencies=}"
        )

    def on_okay_released(self):
        self.start_install_thread()

    def close(self):
        if self._config_updated_hook in self.app.config_updated_hooks:
            self.app.config_updated_hooks.remove(self._config_updated_hook)
        self.app.clear_status()
        self.win.close()

    def on_cancel_released(self):
        self.close()

    def start_install_thread(self):
        self.app.status("Ready to install!", 0)
        self.set_input_widgets_state("disabled")

        def install_in_thread():
            self.app._dispatch(self.close)
            installer.install(self.app)

        self.start_thread(install_in_thread)


def start_gui_app(
    ephemeral_config: EphemeralConfiguration,
    recovery: Optional[Callable[[App], None]] = None,
    install_only: bool = False,
):
    """Open the GUI (gui_main.MainWindow). With `recovery`, repair first; with
    `install_only`, start installing straight away."""
    from . import gui_main

    if recovery is None:
        return gui_main.start(ephemeral_config, install=install_only)

    app = gui_main._qt_app()
    root = Root()
    root.setWindowTitle(f"{constants.APP_NAME}")
    status_gui = gui.StatusWithLabelGui(root, "Repairing your Logos install")
    root.set_content(status_gui)
    root.adjustSize()
    root.show()
    recovery_app = GuiApp(root, status_gui, ephemeral_config)

    def recover():
        try:
            recovery(recovery_app)
        except Exception:
            logging.exception("Recovery failed")
        recovery_app._dispatch(lambda: gui_main.MainWindow(root, ephemeral_config))

    threading.Thread(target=recover, name=f"{constants.APP_NAME} recovery", daemon=True).start()
    return app.exec()
