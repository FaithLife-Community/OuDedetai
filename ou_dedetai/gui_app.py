import copy
import logging
import shutil
import sys
import threading
import time
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ou_dedetai.app import App, UserExitedFromAsk
from ou_dedetai.config import EphemeralConfiguration
from ou_dedetai.constants import (
    PROMPT_OPTION_DIRECTORY,
    PROMPT_OPTION_FILE,
    PROMPT_OPTION_NEW_FILE,
)
import ou_dedetai
import ou_dedetai.logos

from . import backup, constants, control, gui, installer, system, utils, wine


class GuiBridge(QtCore.QObject):
    invoke = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.invoke.connect(self._run, QtCore.Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot(object)
    def _run(self, request):
        callback, event, result = request
        try:
            result["value"] = callback()
        except Exception as exc:
            result["error"] = exc
        finally:
            event.set()


class Root(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.classname = kwargs.get("className", constants.BINARY_NAME)
        self.icon = constants.APP_IMAGE_DIR / "icon.png"
        self.setWindowIcon(QtGui.QIcon(str(self.icon)))

    def set_content(self, widget):
        self.setCentralWidget(widget)


class Toplevel(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowIcon(QtGui.QIcon(str(constants.APP_IMAGE_DIR / "icon.png")))


class GuiApp(App):
    """Implements the App interface for the GUI."""

    _exit_option: Optional[str] = None

    def __init__(
        self,
        root: Root,
        status_gui: gui.StatusGui,
        ephemeral_config: EphemeralConfiguration,
        **kwargs,
    ):
        super().__init__(ephemeral_config)
        self.root = root
        self._status_gui = status_gui
        self._bridge = GuiBridge(root)
        self.start_thread(self.populate_defaults)

    def _is_gui_thread(self):
        return QtCore.QThread.currentThread() == self.root.thread()

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
        result = QtWidgets.QFileDialog.getExistingDirectory(
            self.root, question, str(Path.home())
        )
        return result or None

    def _select_file(self, question):
        result, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.root, question, str(Path.home())
        )
        return result or None

    def _save_file(self, question):
        result, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.root, question, str(Path.home())
        )
        return result or None

    def _info(self, message):
        self._dispatch(lambda: InfoPopUp(message, self.root).exec())

    def _pop_up(self, title, message):
        self._dispatch(
            lambda: QtWidgets.QMessageBox.information(
                self.root, title, message
            )
        )

    def _status(self, message, percent=None):
        self._status_gui.set_status(message, percent)

    def clear_status(self):
        self._status_gui.set_status('', 0)

    def approve(self, question: str, context: str | None = None) -> bool:
        message = f"{question}\n\n{context or ''}".strip()
        return bool(self._dispatch(
            lambda: QtWidgets.QMessageBox.question(
                self.root,
                question,
                message,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            ) == QtWidgets.QMessageBox.StandardButton.Yes
        ))

    def _schedule_exit_on_main_thread(self, reason: str, intended: bool):
        self._dispatch(lambda: self.exit(reason, intended), wait=False)

    def _exit(self, reason: str, intended: bool = False):
        if not intended:
            self._dispatch(
                lambda: QtWidgets.QMessageBox.critical(
                    self.root,
                    "Error",
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
        self.setWindowTitle("Question")
        self.answer = None

        self.gui = gui.ChoiceGui(self, question, options)
        layout = QtWidgets.QVBoxLayout(self)
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
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
        ):
            self.confirm()
            return
        super().keyPressEvent(event)


class InfoPopUp(Toplevel):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Info")

        self.gui = gui.InfoGui(self, message)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.gui)

        self.gui.okay_button.clicked.connect(self.accept)
        self.resize(self.sizeHint())

    def keyPressEvent(self, event):
        if event.key() in (
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
            QtCore.Qt.Key.Key_Escape,
        ):
            self.accept()
            return
        super().keyPressEvent(event)


class InstallerWindow:
    def __init__(self, new_win, root: Root, app: GuiApp, **kwargs):
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
            & ~QtCore.Qt.WindowType.WindowMaximizeButtonHint
        )

        layout = QtWidgets.QVBoxLayout(self.win)
        layout.addWidget(self.gui)

        self.gui.product_dropdown.currentTextChanged.connect(self.set_product)
        self.gui.version_dropdown.currentTextChanged.connect(self.set_version)
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
        if watched is self.win and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() in (
                QtCore.Qt.Key.Key_Return,
                QtCore.Qt.Key.Key_Enter,
            ):
                self.on_okay_released()
                return True
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.on_cancel_released()
                return True
        return super().eventFilter(watched, event)

    def _config_updated_hook(self):
        self.app._dispatch(self._update_config_gui, wait=False)

    def _update_config_gui(self):
        self.gui.product_dropdown.blockSignals(True)
        self.gui.version_dropdown.blockSignals(True)
        self.gui.release_dropdown.blockSignals(True)
        self.gui.wine_dropdown.blockSignals(True)
        self.gui.skipdeps_checkbox.blockSignals(True)

        self.gui.product_dropdown.setCurrentText(
            self.conf.faithlife_product or ""
        )
        self.gui.version_dropdown.setCurrentText(
            self.conf.faithlife_product_version or ""
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
        self.gui.version_dropdown.blockSignals(False)
        self.gui.release_dropdown.blockSignals(False)
        self.gui.wine_dropdown.blockSignals(False)
        self.gui.skipdeps_checkbox.blockSignals(False)

        self.root.setWindowIcon(
            QtGui.QIcon(str(self.conf.faithlife_product_icon_path))
        )
        self.set_input_widgets_state("enabled", [self.gui.okay_button])

    def _post_dropdown_change(self):
        self.installer_step = 0
        self.installer_step_count = 0
        self.conf.install_dir = self.conf.install_dir_default

    def set_input_widgets_state(self, state, widgets="all"):
        enabled = state == "enabled"
        all_widgets = [
            self.gui.product_dropdown,
            self.gui.version_dropdown,
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

    def set_version(self, value):
        if value:
            self.conf.faithlife_product_version = value
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


class ControlWindow(GuiApp):
    def __init__(
        self,
        root,
        control_gui: gui.ControlGui,
        ephemeral_config: EphemeralConfiguration,
        *args,
        **kwargs,
    ):
        super().__init__(root, control_gui, ephemeral_config)
        self.root = root
        self.gui = control_gui
        self.actioncmd: Optional[Callable[[], None]] = None

        version = constants.LLI_CURRENT_VERSION
        self.gui.update_lli_label.setText(
            f"Update {constants.APP_NAME}\ncurrent: v{version}\nlatest: ..."
        )
        self.gui.update_lli_button.setEnabled(False)

        def update_lli_version():
            text = (
                f"Update {constants.APP_NAME}\n"
                f"current: v{version}\n"
                f"latest: v{self.conf.app_latest_version}"
            )
            self._dispatch(
                lambda: self.gui.update_lli_label.setText(text)
            )
            self.update_latest_lli_release_button()

        self.start_thread(update_lli_version)

        if self.conf._raw.faithlife_product:
            self.gui.update_product_label.setText(
                f"Update {self.conf._raw.faithlife_product}"
            )

        def monitor_faithlife_product_pids():
            last_state = copy.copy(self.logos.logos_state)
            while True:
                if self.is_installed():
                    self.logos.monitor()
                    time.sleep(1)
                else:
                    time.sleep(30)

                if last_state != self.logos.logos_state:
                    self.update_app_button()
                last_state = copy.copy(self.logos.logos_state)

        self.start_thread(monitor_faithlife_product_pids)

        self.gui.run_indexing_radio.toggled.connect(self.on_action_radio_clicked)
        self.gui.remove_library_catalog_radio.toggled.connect(
            self.on_action_radio_clicked
        )
        self.gui.remove_index_files_radio.toggled.connect(
            self.on_action_radio_clicked
        )
        self.gui.uninstall_radio.toggled.connect(self.on_action_radio_clicked)
        self.gui.install_icu_radio.toggled.connect(self.on_action_radio_clicked)

        self.gui.actions_button.clicked.connect(self.run_action_cmd)

        self.gui.logging_button.setText("Enable")
        self.gui.logging_button.clicked.connect(self.switch_logging)
        self.gui.logging_button.setEnabled(False)

        self.gui.support_button.clicked.connect(self.get_support)
        self.gui.config_button.clicked.connect(self.edit_config)
        self.gui.deps_button.clicked.connect(self.install_deps)
        self.gui.backup_button.clicked.connect(self.run_backup)
        self.gui.restore_button.clicked.connect(self.run_restore)
        self.gui.update_product_button.clicked.connect(
            self.update_faithlife_product
        )
        self.gui.update_lli_button.clicked.connect(
            self.update_to_latest_lli_release
        )
        self.gui.latest_appimage_button.clicked.connect(
            self.start_appimage_update
        )
        self.gui.set_appimage_button.clicked.connect(self.set_appimage)

        self._config_update_hook()
        self.config_updated_hooks.append(self._config_update_hook)

    def edit_config(self):
        control.edit_file(self.conf.config_file_path)

    def run_install(self):
        def install_in_thread():
            try:
                self.populate_defaults()
                installer.install(self)
            except UserExitedFromAsk:
                self.populate_defaults()
            finally:
                self._dispatch(
                    lambda: (
                        self.gui.app_button.setEnabled(True),
                        self.gui.app_install_advanced.setEnabled(True),
                    ),
                    wait=False,
                )

        self.gui.app_button.setEnabled(False)
        self.gui.app_install_advanced.setEnabled(False)
        self.start_thread(install_in_thread)

    def run_installer(self):
        dialog = Toplevel(self.root)
        InstallerWindow(dialog, self.root, self)
        dialog.exec()

    def stop_logos(self):
        self.start_thread(self.logos.stop)

    def run_logos(self):
        self.start_thread(self.logos.start)

    def run_action_cmd(self):
        if self.actioncmd:
            self.actioncmd()

    def on_action_radio_clicked(self, action):
        logging.debug("gui_app.ControlWindow.on_action_radio_clicked START")
        if not self.is_installed():
            return

        actions = {
            'run-indexing': self.run_indexing,
            'remove-library-catalog': self.remove_library_catalog,
            'remove-index-files': self.remove_indexes,
            'install-icu': self.install_icu,
            'uninstall': self.uninstall,
        }
        self.actioncmd = actions.get(action)
        self.gui.actions_button.setEnabled(self.actioncmd is not None)

    def run_indexing(self):
        self.start_thread(self.logos.index)

    def remove_library_catalog(self):
        self.start_thread(control.remove_library_catalog, self)

    def remove_indexes(self):
        self._status("Removing indexes…")
        self.start_thread(control.remove_all_index_files, app=self)

    def install_icu(self):
        self._status("Installing ICU files…")
        self.start_thread(wine.enforce_icu_data_files, app=self)

    def uninstall(self):
        def run():
            control.uninstall(self)
            self.clear_status()
            self.populate_defaults()
        self.start_thread(run)

    def run_backup(self):
        self.gui.progress.setRange(0, 100)
        self.gui.progress.setValue(0)
        self.gui.progress.show()
        self.start_thread(backup.backup, app=self)

    def run_restore(self):
        self.start_thread(backup.restore, app=self)

    def install_deps(self):
        self.start_thread(utils.install_dependencies, self)

    def open_file_dialog(self, filetype_name, filetype_extension):
        def select_file():
            result, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.root,
                f"Select {filetype_name}",
                str(Path.home()),
                f"{filetype_name} (*.{filetype_extension});;All Files (*)",
            )
            return result or None
        return self._dispatch(select_file)

    def update_faithlife_product(self):
        self.status(
            f"Updating {self.conf.faithlife_product} to latest release…"
        )
        self.start_thread(utils.update_faithlife_product, app=self)

    def update_to_latest_lli_release(self):
        self.status(f"Updating to latest {constants.APP_NAME} version…")
        self.start_thread(utils.update_to_latest_lli_release, app=self)

    def set_appimage_symlink(self):
        utils.set_appimage_symlink(self)
        self.update_latest_appimage_button()

    def start_appimage_update(self):
        self.status("Updating to latest AppImage…")
        self.gui.latest_appimage_button.setEnabled(False)
        self.start_thread(self.update_to_latest_appimage)

    def update_to_latest_appimage(self):
        utils.update_to_latest_recommended_appimage(self)
        self._dispatch(self.update_latest_appimage_button, wait=False)

    def set_appimage(self):
        filename = self.open_file_dialog("AppImage", "AppImage")
        if not filename:
            return
        self.conf.wine_appimage_path = filename
        self.start_thread(self.set_appimage_symlink)

    def switch_logging(self):
        desired_state = self.gui.logging_button.text()
        self._status(f"Switching app logging to '{desired_state}d'…")
        self.gui.logging_button.setEnabled(False)
        self.start_thread(
            self.logos.switch_logging,
            action=desired_state.lower(),
        )

    def get_support(self):
        self.start_thread(control.get_support, self)

    def update_logging_button(self):
        if not self._is_gui_thread():
            self._dispatch(self.update_logging_button, wait=False)
            return
        state = self.reverse_logging_state_value(
            self.current_logging_state_value()
        )
        self.gui.logging_button.setText(state[:-1].title())
        self.gui.logging_button.setEnabled(True)

    def update_app_button(self):
        if not self._is_gui_thread():
            self._dispatch(self.update_app_button, wait=False)
            return

        self.gui.app_button.setEnabled(True)

        try:
            self.gui.app_button.clicked.disconnect()
        except RuntimeError:
            pass

        if self.is_installed():
            if self.logos.logos_state == ou_dedetai.logos.State.RUNNING:
                self.gui.app_button.setText(
                    f"Stop {self.conf.faithlife_product}"
                )
                self.gui.app_button.clicked.connect(self.stop_logos)
            else:
                self.gui.app_button.setText(
                    f"Run {self.conf.faithlife_product}"
                )
                self.gui.app_button.clicked.connect(self.run_logos)

            self.gui.logging_button.setEnabled(True)
            self.gui.app_install_advanced.hide()
            self.gui.actions_button.setEnabled(True)
        else:
            self.gui.app_button.setText("Install")
            self.gui.app_button.clicked.connect(self.run_install)
            self.gui.app_install_advanced.setEnabled(True)
            self.gui.app_install_advanced.show()
            self.gui.actions_button.setEnabled(False)

            ready = all(value is not None for value in (
                self.conf._raw.faithlife_product,
                self.conf._raw.faithlife_product_version,
                self.conf._raw.faithlife_product_release_channel,
                self.conf._raw.faithlife_product_release,
            ))
            self.gui.app_button.setEnabled(ready)
            self.gui.app_install_advanced.setEnabled(ready)

    def update_product_button(self):
        if not self._is_gui_thread():
            self._dispatch(self.update_product_button, wait=False)
            return

        if not self.is_installed():
            enabled = False
            message = "Please install first."
        elif self.conf.is_installed_faithlife_product_release_latest:
            enabled = False
            message = f"{self.conf.faithlife_product} is up-to-date."
        else:
            enabled = True
            message = ""

        self.gui.update_product_button.setToolTip(message)
        self.gui.update_product_button.setEnabled(enabled)

    def update_latest_lli_release_button(self):
        if not self._is_gui_thread():
            self._dispatch(
                self.update_latest_lli_release_button,
                wait=False,
            )
            return

        result = utils.compare_logos_linux_installer_version(self)
        if constants.RUNMODE != "binary":
            enabled = False
            message = f"Can't run self-update from {constants.RUNMODE}."
        elif result == utils.VersionComparison.OUT_OF_DATE:
            enabled = True
            message = ""
        elif result == utils.VersionComparison.UP_TO_DATE:
            enabled = False
            message = f"{constants.APP_NAME} is up-to-date."
        elif result == utils.VersionComparison.DEVELOPMENT:
            enabled = False
            message = (
                f"{constants.APP_NAME} is newer than the latest release."
            )
        else:
            enabled = False
            message = ""

        self.gui.update_lli_button.setToolTip(message)
        self.gui.update_lli_button.setEnabled(enabled)

    def update_latest_appimage_button(self):
        if not self._is_gui_thread():
            self._dispatch(
                self.update_latest_appimage_button,
                wait=False,
            )
            return

        if not self.is_installed():
            enabled = False
            message = "Please install first."
        elif self.conf._raw.wine_binary_code not in (
            "Recommended", "AppImage", None
        ):
            enabled = False
            message = (
                "The configured install was not created using an AppImage."
            )
            self.gui.set_appimage_button.setEnabled(False)
            self.gui.set_appimage_button.setToolTip(message)
        elif self.conf._raw.wine_binary is not None:
            status, _ = utils.compare_recommended_appimage_version(self)
            if status == 0:
                enabled, message = True, ""
            elif status == 1:
                enabled = False
                message = (
                    "The AppImage is already set to the latest recommended."
                )
            elif status == 2:
                enabled = False
                message = (
                    "The AppImage version is newer than the latest recommended."
                )
            else:
                enabled, message = True, ""
        else:
            enabled, message = True, ""

        self.gui.latest_appimage_button.setToolTip(message)
        self.gui.latest_appimage_button.setEnabled(enabled)

    def _config_update_hook(self, evt=None):
        if not self._is_gui_thread():
            self._dispatch(self._config_update_hook, wait=False)
            return

        self.update_logging_button()
        self.update_app_button()

        for callback, name in (
            (self.update_latest_lli_release_button, "release button"),
            (self.update_latest_appimage_button, "AppImage button"),
            (self.update_product_button, "product button"),
        ):
            try:
                callback()
            except Exception:
                logging.exception("Failed to update %s", name)

        product = self.conf._raw.faithlife_product
        if product:
            self.gui.update_product_label.setText(f"Update {product}")

    def current_logging_state_value(self):
        return "ENABLED" if self.conf.faithlife_product_logging else "DISABLED"

    def reverse_logging_state_value(self, state):
        return "ENABLED" if state == "DISABLED" else "DISABLED"


def set_style(app):
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(
        QtGui.QPalette.ColorRole.Window,
        QtGui.QColor(constants.LOGOS_WHITE),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.Base,
        QtGui.QColor(constants.LOGOS_WHITE),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.Button,
        QtGui.QColor(constants.LOGOS_GRAY),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.Highlight,
        QtGui.QColor(constants.LOGOS_BLUE),
    )
    app.setPalette(palette)


def start_gui_app(
    ephemeral_config: EphemeralConfiguration,
    recovery: Optional[Callable[[App], None]] = None,
    install_only: bool = False,
):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget {
            background-color: #252525;
            color: #eeeeee;
            font-size: 10pt;
        }
        QLabel {
            color: #eeeeee;
        }
        QPushButton {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #606060;
            border-radius: 4px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #505050;
        }
        QComboBox, QLineEdit, QPlainTextEdit {
            background-color: #333333;
            color: #ffffff;
            border: 1px solid #606060;
            padding: 4px;
        }
        QRadioButton, QCheckBox {
            color: #eeeeee;
        }
    """)

    root = Root()
    root.setWindowTitle(f"{constants.APP_NAME} Control Panel")

    if install_only:
        status_gui = gui.StatusWithLabelGui(
            root, "Installing FaithLife app"
        )
        root.set_content(status_gui)
        root.adjustSize()
        root.show()

        gui_app = GuiApp(root, status_gui, ephemeral_config)

        def install():
            try:
                gui_app.populate_defaults()
                installer.install(gui_app)
                time.sleep(3)
            except Exception:
                logging.exception("Installation failed")
            finally:
                gui_app._dispatch(root.close, wait=False)

        threading.Thread(
            target=install,
            name=f"{constants.APP_NAME} installer",
            daemon=True,
        ).start()

    elif recovery:
        status_gui = gui.StatusWithLabelGui(
            root, "Recovering FaithLife app"
        )
        root.set_content(status_gui)
        root.adjustSize()
        root.show()

        recovery_app = GuiApp(root, status_gui, ephemeral_config)

        def recover():
            try:
                recovery(recovery_app)
            except Exception:
                logging.exception("Recovery failed")

            def show_control_panel():
                control_gui = gui.ControlGui(root)
                root.set_content(control_gui)
                ControlWindow(root, control_gui, ephemeral_config)
                root.setWindowTitle(
                    f"{constants.APP_NAME} Control Panel"
                )
                root.adjustSize()
                root.show()

            recovery_app._dispatch(show_control_panel)

        threading.Thread(
            target=recover,
            name=f"{constants.APP_NAME} recovery",
            daemon=True,
        ).start()

    else:
        control_gui = gui.ControlGui(root)
        root.set_content(control_gui)
        ControlWindow(root, control_gui, ephemeral_config)
        root.adjustSize()
        root.show()

    return app.exec()
