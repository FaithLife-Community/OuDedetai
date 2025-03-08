
# References:
#   - https://tkdocs.com/
#   - https://github.com/thw26/LogosLinuxInstaller/blob/master/LogosLinuxInstaller.sh  # noqa: E501

import logging
from pathlib import Path
from queue import Queue

import shutil
from threading import Event
import threading
import time
from tkinter import PhotoImage, messagebox
from tkinter import Tk
from tkinter import Toplevel as TkToplevel
from tkinter import filedialog as fd
from tkinter.ttk import Style
from typing import Callable, Optional

from ou_dedetai.app import App, UserExitedFromAsk
from ou_dedetai.constants import (
    PROMPT_OPTION_DIRECTORY,
    PROMPT_OPTION_FILE,
    PROMPT_OPTION_NEW_FILE,
)
from ou_dedetai.config import EphemeralConfiguration

from . import constants
from . import control
from . import gui
from . import installer
from . import system
from . import utils
from . import wine

class GuiApp(App):
    """Implements the App interface for all windows"""

    _exit_option: Optional[str] = None

    def __init__(self, root: "Root", gui: gui.StatusGui, ephemeral_config: EphemeralConfiguration, **kwargs): #noqa: E501
        super().__init__(ephemeral_config)
        self.root = root
        self._status_gui = gui
        # Now spawn a new thread to ensure choices are set to set to defaults so user
        # isn't App.ask'ed
        def _populate_initial_defaults():
            self.populate_defaults()
        self.start_thread(_populate_initial_defaults)


    def _ask(self, question: str, options: list[str] | str) -> Optional[str]:
        # This cannot be run from the main thread as the dialog will never appear
        # since the tinker mainloop hasn't started and we block on a response

        if isinstance(options, list):
            answer_q: Queue[Optional[str]] = Queue()
            answer_event = Event()
            ChoicePopUp(question, options, answer_q, answer_event)

            answer_event.wait()
            answer: Optional[str] = answer_q.get()
        elif isinstance(options, str):
            answer = options

        if answer == PROMPT_OPTION_DIRECTORY:
            answer = fd.askdirectory(
                parent=self.root,
                title=question,
                initialdir=Path().home(),
            )
        elif answer == PROMPT_OPTION_FILE:
            answer = fd.askopenfilename(
                parent=self.root,
                title=question,
                initialdir=Path().home(),
            )
        elif answer == PROMPT_OPTION_NEW_FILE:
            answer = fd.asksaveasfilename(
                parent=self.root,
                title=question,
                initialdir=Path().home(),
            )
        return answer

    def _info(self, message):
        """Display information to the user"""
        InfoPopUp(message)

    def _status(self, message, percent = None):
        message = message.lstrip("\r")
        if percent is not None:
            self._status_gui.progress.stop()
            self._status_gui.progress.state(['disabled'])
            self._status_gui.progress.config(mode='determinate')
            self._status_gui.progressvar.set(percent)
        else:
            self._status_gui.progress.state(['!disabled'])
            self._status_gui.progressvar.set(0)
            self._status_gui.progress.config(mode='indeterminate')
            self._status_gui.progress.start()
        self._status_gui.statusvar.set(message)

    def clear_status(self):
        self._status('', 0)

    def approve(self, question: str, context: str | None = None) -> bool:
        if context is None:
            context = ""
        message = f"{question}\n\n{context}"
        return messagebox.askquestion(question, message.strip()) == 'yes'

    def _exit(self, reason: str, intended: bool = False):
        # Create a little dialog before we die so the user can see why this happened
        if not intended:
            gui.show_error(reason, detail=constants.SUPPORT_MESSAGE, fatal=False)
        self.root.destroy()
    
    @property
    def superuser_command(self) -> str:
        """Command when root privileges are needed.
        
        Raises:
            SuperuserCommandNotFound - if no command is found

        pkexec if found"""
        if shutil.which('pkexec'):
            return "pkexec"
        else:
            raise system.SuperuserCommandNotFound("No superuser command found. Please install pkexec.")  # noqa: E501
    
    def populate_defaults(self) -> None:
        """If any prompt is unset, set it to it's default value
        
        Useful for startign the UI at an installable state,
        the user can change these choices later"""

        # For the GUI, use defaults until user says otherwise.
        if self.conf._raw.faithlife_product is None:
            self.conf.faithlife_product = constants.FAITHLIFE_PRODUCTS[0]
        if self.conf._raw.faithlife_product_version is None:
            self.conf.faithlife_product_version = constants.FAITHLIFE_PRODUCT_VERSIONS[0] #noqa: E501

        # Now that we know product and version are set we can download the releases
        # And use the first one
        # Also ensure that our network cache is populated
        if self.conf._network._faithlife_product_releases(
            self.conf._raw.faithlife_product,
            self.conf._raw.faithlife_product_version,
            self.conf._raw.faithlife_product_release_channel,
        ):
            if self.conf._raw.faithlife_product_release is None:
                self.conf.faithlife_product_release = self.conf.faithlife_product_releases[0] #noqa: E501
        else:
            # Spawn a thread that does this, as the download takes a second
            def _populate_product_release_default():
                # Always Get the latest release
                latest_release = self.conf.faithlife_product_releases[0]
                # If the release wasn't set before, set it now
                if self.conf._raw.faithlife_product_release is None:
                    self.conf.faithlife_product_release = latest_release
            self.start_thread(_populate_product_release_default)

        # Set the install_dir to default, no option in the GUI to change it
        if self.conf._raw.install_dir is None:
            self.conf.install_dir = self.conf.install_dir_default

        if self.conf._raw.wine_binary is None:
            wine_choices = utils.get_wine_options(self)
            if len(wine_choices) > 0:
                self.conf.wine_binary = wine_choices[0]

class Root(Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.classname = kwargs.get('classname')
        # Set the theme.
        set_style(self)

        # Make root widget's outer border expand with window.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Set panel icon.
        self.icon = constants.APP_IMAGE_DIR / 'icon.png'
        self.pi = PhotoImage(file=f'{self.icon}', master=self)
        self.iconphoto(False, self.pi)


class Toplevel(TkToplevel):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        set_style(self)

        # Make root widget's outer border expand with window.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)


class ChoicePopUp:
    """Creates a pop-up with a choice"""
    def __init__(self, question: str, options: list[str], answer_q: Queue[Optional[str]], answer_event: Event, **kwargs): #noqa: E501
        self.root = Toplevel()
        # Set root parameters.
        self.gui = gui.ChoiceGui(self.root, question, options)
        self.root.title("Question")
        # Set root widget event bindings.
        self.root.bind(
            "<Return>",
            self.on_confirm_choice
        )
        self.root.bind(
            "<Escape>",
            self.on_cancel_released
        )
        self.gui.cancel_button.config(command=self.on_cancel_released)
        self.gui.okay_button.config(command=self.on_confirm_choice)
        self.answer_q = answer_q
        self.answer_event = answer_event

    def on_confirm_choice(self, evt=None):
        if self.gui.answer_dropdown.get() == gui.ChoiceGui._default_prompt:
            return
        answer = self.gui.answer_dropdown.get()
        self.answer_q.put(answer)
        self.answer_event.set()
        self.root.destroy()

    def on_cancel_released(self, evt=None):
        self.answer_q.put(None)
        self.answer_event.set()
        self.root.destroy()


class InfoPopUp:
    """Creates a pop-up with info shared to the user"""
    def __init__(self, message: str, **kwargs):
        self.root = Toplevel()
        # Set root parameters.
        self.gui = gui.InfoGui(self.root, message)
        self.root.title("Info")
        # Set root widget event bindings.
        self.root.bind(
            "<Return>",
            self.on_okay_released
        )
        self.root.bind(
            "<Escape>",
            self.on_okay_released
        )
        self.gui.okay_button.config(command=self.on_okay_released)

    def on_okay_released(self, evt=None):
        self.root.destroy()


class InstallerWindow:
    def __init__(self, new_win, root: Root, app: "GuiApp", **kwargs):
        # Set root parameters.
        self.win = new_win
        self.root = root
        self.win.title(f"{constants.APP_NAME} Installer")
        self.win.resizable(False, False)
        self.gui = gui.InstallerGui(self.win, app)
        self.app = app
        self.conf = app.conf
        self.start_thread = app.start_thread

        # Initialize variables.
        self.config_thread = None

        # Set widget callbacks and event bindings.
        self.gui.product_dropdown.bind(
            '<<ComboboxSelected>>',
            self.set_product
        )
        self.gui.version_dropdown.bind(
            '<<ComboboxSelected>>',
            self.set_version
        )
        self.gui.release_dropdown.bind(
            '<<ComboboxSelected>>',
            self.set_release
        )
        self.gui.wine_dropdown.bind(
            '<<ComboboxSelected>>',
            self.set_wine
        )
        self.gui.skipdeps_checkbox.config(command=self.set_skip_dependencies)
        self.gui.cancel_button.config(command=self.on_cancel_released)
        self.gui.okay_button.config(command=self.on_okay_released)

        # Set root widget event bindings.
        self.root.bind(
            "<Return>",
            self.on_okay_released
        )
        self.root.bind(
            "<Escape>",
            self.on_cancel_released
        )

        # Run commands.
        self.app.config_updated_hooks += [self._config_updated_hook]
        # Start out enforcing this
        self._config_updated_hook()

    def _config_updated_hook(self):
        """Update the GUI to reflect changes in the configuration/network""" #noqa: E501

        self.app.populate_defaults()

        # Fill in the UI elements from the config
        self.gui.productvar.set(self.conf.faithlife_product)
        self.gui.versionvar.set(self.conf.faithlife_product_version) # noqa: E501

        # Now that we know product and version are set we can download the releases
        self.gui.release_dropdown['values'] = self.conf.faithlife_product_releases
        self.gui.releasevar.set(self.conf.faithlife_product_release)

        self.gui.skipdepsvar.set(not self.conf.skip_install_system_dependencies)

        # In case the product changes
        self.root.icon = Path(self.conf.faithlife_product_icon_path)

        self.gui.wine_dropdown['values'] = utils.get_wine_options(self.app)
        if not self.gui.winevar.get():
            # If no value selected, default to 1st item in list.
            self.gui.winevar.set(self.gui.wine_dropdown['values'][0])

        self.gui.winevar.set(self.conf._raw.wine_binary or '')

        # At this point all variables are populated, we're ready to install!
        self.set_input_widgets_state('enabled', [self.gui.okay_button])

    def _post_dropdown_change(self):
        """Steps to preform after a dropdown has been updated"""
        # Ensure progress counter is reset.
        self.installer_step = 0
        self.installer_step_count = 0
        # Reset install_dir to default based on possible new value
        self.conf.install_dir = self.conf.install_dir_default

    def set_input_widgets_state(self, state, widgets='all'):
        if state == 'enabled':
            state = ['!disabled']
        elif state == 'disabled':
            state = ['disabled']
        all_widgets = [
            self.gui.product_dropdown,
            self.gui.version_dropdown,
            self.gui.release_dropdown,
            self.gui.wine_dropdown,
            self.gui.okay_button,
        ]
        if widgets == 'all':
            widgets = all_widgets
        for w in widgets:
            w.state(state)

    def set_product(self, evt=None):
        self.conf.faithlife_product = self.gui.productvar.get()
        self.gui.product_dropdown.selection_clear()
        self._post_dropdown_change()

    def set_version(self, evt=None):
        self.conf.faithlife_product_version = self.gui.versionvar.get()
        self.gui.version_dropdown.selection_clear()
        self._post_dropdown_change()

    def set_release(self, evt=None):
        self.conf.faithlife_product_release = self.gui.releasevar.get()
        self.gui.release_dropdown.selection_clear()
        self._post_dropdown_change()

    def set_wine(self, evt=None):
        self.conf.wine_binary = self.gui.winevar.get()
        self.gui.wine_dropdown.selection_clear()
        self._post_dropdown_change()

    def set_skip_dependencies(self, evt=None):
        self.conf.skip_install_system_dependencies = self.gui.skipdepsvar.get()  # invert True/False  # noqa: E501
        logging.debug(f"> {self.conf.skip_install_system_dependencies=}") #noqa: E501

    def on_okay_released(self, evt=None):
        # Update desktop panel icon.
        self.start_install_thread()

    def close(self):
        self.app.config_updated_hooks.remove(self._config_updated_hook)
        # Reset status
        self.app.clear_status()
        self.win.destroy()

    def on_cancel_released(self, evt=None):
        self.app.clear_status()
        self.close()
        return 1

    def start_install_thread(self, evt=None):
        def _install():
            """Function to handle the install"""
            # Close the options window and let the install run
            self.close()
            installer.install(self.app)
            # Install complete, cleaning up...
            return 0

        # Setup for the install
        self.app.status('Ready to install!', 0)
        self.set_input_widgets_state('disabled')

        self.start_thread(_install)


class ControlWindow(GuiApp):
    def __init__(self, root, control_gui: gui.ControlGui, 
                 ephemeral_config: EphemeralConfiguration, *args, **kwargs):
        super().__init__(root, control_gui, ephemeral_config)

        # Set root parameters.
        self.root = root
        self.gui = control_gui
        self.actioncmd: Optional[Callable[[], None]] = None

        ver = constants.LLI_CURRENT_VERSION
        text = f"Update {constants.APP_NAME}\ncurrent: v{ver}\nlatest: ..." #noqa: E501
        # Spawn a thread to update the label with the current version
        def _update_lli_version():
            text = f"Update {constants.APP_NAME}\ncurrent: v{ver}\nlatest: v{self.conf.app_latest_version}" #noqa: E501
            self.gui.update_lli_label.config(text=text)
            self.update_latest_lli_release_button()
        self.gui.update_lli_button.state(['disabled'])
        self.start_thread(_update_lli_version)
        self.gui.update_lli_label.config(text=text)
        self.gui.run_indexing_radio.config(
            command=self.on_action_radio_clicked
        )
        self.gui.remove_library_catalog_radio.config(
            command=self.on_action_radio_clicked
        )
        self.gui.remove_index_files_radio.config(
            command=self.on_action_radio_clicked
        )
        self.gui.uninstall_radio.config(
            command=self.on_action_radio_clicked
        )
        self.gui.install_icu_radio.config(
            command=self.on_action_radio_clicked
        )
        self.gui.actions_button.config(command=self.run_action_cmd)

        self.gui.loggingstatevar.set('Enable')
        self.gui.logging_button.config(
            text=self.gui.loggingstatevar.get(),
            command=self.switch_logging
        )
        self.gui.logging_button.state(['disabled'])
        self.gui.support_button.config(command=self.get_support)

        self.gui.config_button.config(command=self.edit_config)
        self.gui.deps_button.config(command=self.install_deps)
        self.gui.backup_button.config(command=self.run_backup)
        self.gui.restore_button.config(command=self.run_restore)
        self.gui.update_lli_button.config(
            command=self.update_to_latest_lli_release
        )
        self.gui.latest_appimage_button.config(
            command=self.start_appimage_update
        )
        self.gui.set_appimage_button.config(command=self.set_appimage)

        self._config_update_hook()
        # These can be expanded to change the UI based on config changes.
        self.config_updated_hooks += [self._config_update_hook]

    def edit_config(self):
        control.edit_file(self.conf.config_file_path)

    def run_install(self, evt=None):
        """Directly install the product.
        
        Fallback to defaults if we don't know a response"""
        def _install():
            try:
                self.populate_defaults()
                installer.install(self)
            except UserExitedFromAsk:
                # Ensure that the defaults are properly set back up
                self.populate_defaults()
            finally:
                # Enable the run button
                self.gui.app_button.state(['!disabled'])
                self.gui.app_install_advanced.state(['!disabled'])
        # Disable the install buttons
        self.gui.app_button.state(['disabled'])
        self.gui.app_install_advanced.state(['disabled'])
        # Start the install thread.
        self.start_thread(_install)

    def run_installer(self, evt=None):
        classname = constants.BINARY_NAME
        installer_window_top = Toplevel()
        InstallerWindow(installer_window_top, self.root, app=self, class_=classname) #noqa: E501

    def run_logos(self, evt=None):
        self.start_thread(self.logos.start)

    def run_action_cmd(self, evt=None):
        if self.actioncmd:
            self.actioncmd()

    def on_action_radio_clicked(self, evt=None):
        logging.debug("gui_app.ControlPanel.on_action_radio_clicked START")
        if self.is_installed():
            self.gui.actions_button.state(['!disabled'])
            if self.gui.actionsvar.get() == 'run-indexing':
                self.actioncmd = self.run_indexing
            elif self.gui.actionsvar.get() == 'remove-library-catalog':
                self.actioncmd = self.remove_library_catalog
            elif self.gui.actionsvar.get() == 'remove-index-files':
                self.actioncmd = self.remove_indexes
            elif self.gui.actionsvar.get() == 'install-icu':
                self.actioncmd = self.install_icu
            elif self.gui.actionsvar.get() == 'uninstall':
                self.actioncmd = self.uninstall

    def run_indexing(self):
        self.start_thread(self.logos.index)

    def remove_library_catalog(self):
        control.remove_library_catalog(self)

    def remove_indexes(self):
        self.gui.statusvar.set("Removing indexes…")
        self.start_thread(control.remove_all_index_files, app=self)

    def install_icu(self):
        self.gui.statusvar.set("Installing ICU files…")
        self.start_thread(wine.enforce_icu_data_files, app=self)

    def uninstall(self):
        def _run():
            control.uninstall(self)
            self.clear_status()
            self.populate_defaults()
        self.start_thread(_run)

    def run_backup(self, evt=None):
        # Prepare progress bar.
        self.gui.progress.state(['!disabled'])
        self.gui.progress.config(mode='determinate')
        self.gui.progressvar.set(0)
        # Start backup thread.
        self.start_thread(control.backup, app=self)

    def run_restore(self, evt=None):
        # FIXME: Allow user to choose restore source?
        # Start restore thread.
        self.start_thread(control.restore, app=self)

    def install_deps(self, evt=None):
        self.start_thread(utils.install_dependencies, self)

    def open_file_dialog(self, filetype_name, filetype_extension):
        file_path = fd.askopenfilename(
            title=f"Select {filetype_name}",
            filetypes=[
                (filetype_name, f"*.{filetype_extension}"),
                ("All Files", "*.*")
            ],
        )
        return file_path

    def update_to_latest_lli_release(self, evt=None):
        self.status(f"Updating to latest {constants.APP_NAME} version…")  # noqa: E501
        self.start_thread(utils.update_to_latest_lli_release, app=self)

    def set_appimage_symlink(self):
        utils.set_appimage_symlink(self)
        self.update_latest_appimage_button()

    def start_appimage_update(self):
        self.status("Updating to latest AppImage…")
        self.gui.latest_appimage_button.state(['disabled'])
        evt = '<<AppImageUpdateDone>>'
        self.root.bind(evt, self.update_latest_appimage_button)
        self.start_thread(self.update_to_latest_appimage, evt=evt)

    def update_to_latest_appimage(self, evt=None):
        utils.update_to_latest_recommended_appimage(self)
        self.root.event_generate(evt)

    def set_appimage(self, evt=None):
        # TODO: Separate as advanced feature.
        appimage_filename = self.open_file_dialog("AppImage", "AppImage")
        if not appimage_filename:
            return
        self.conf.wine_appimage_path = appimage_filename
        self.start_thread(self.set_appimage_symlink)

    def switch_logging(self, evt=None):
        desired_state = self.gui.loggingstatevar.get()
        self._status(f"Switching app logging to '{desired_state}d'…")
        self.gui.logging_button.state(['disabled'])
        self.start_thread(
            self.logos.switch_logging,
            action=desired_state.lower()
        )

    def get_support(self):
        def _run():
            control.get_support(self)
        self.start_thread(_run)

    def update_logging_button(self, evt=None):
        state = self.reverse_logging_state_value(self.current_logging_state_value())
        self.gui.loggingstatevar.set(state[:-1].title())
        self.gui.logging_button.state(['!disabled'])

    def update_app_button(self, evt=None):
        self.gui.app_button.state(['!disabled'])
        if self.is_installed():
            self.gui.app_buttonvar.set(f"Run {self.conf.faithlife_product}")
            self.gui.app_button.config(command=self.run_logos)
            self.gui.logging_button.state(['!disabled'])
            self.gui.app_install_advanced.grid_forget()
            self.gui.actions_button.state(['!disabled'])
        else:
            self.gui.app_buttonvar.set("Install")
            self.gui.app_button.config(command=self.run_install)
            self.gui.app_install_advanced.config(command=self.run_installer)
            self.gui.show_advanced_install_button()
            self.gui.actions_button.state(['disabled'])
            # Make sure the product/version/channel/release is non-None
            if None not in [
                self.conf._raw.faithlife_product,
                self.conf._raw.faithlife_product_version,
                self.conf._raw.faithlife_product_release_channel,
                self.conf._raw.faithlife_product_release
            ]:
                # Everything is ready, we can install
                self.gui.app_button.state(['!disabled'])
                self.gui.app_install_advanced.state(['!disabled'])
            else:
                # Disable Both install buttons
                self.gui.app_button.state(['disabled'])
                self.gui.app_install_advanced.state(['disabled'])

    def update_latest_lli_release_button(self, evt=None):
        msg = None
        result = utils.compare_logos_linux_installer_version(self)
        if constants.RUNMODE != 'binary':
            state = 'disabled'
            msg = f"This button is disabled. Can't run self-update from {constants.RUNMODE}."  # noqa: E501
        elif result == utils.VersionComparison.OUT_OF_DATE:
            state = '!disabled'
        elif result == utils.VersionComparison.UP_TO_DATE:
            state = 'disabled'
            msg = f"This button is disabled. {constants.APP_NAME} is up-to-date."  # noqa: E501
        elif result == utils.VersionComparison.DEVELOPMENT:
            state = 'disabled'
            msg = f"This button is disabled. {constants.APP_NAME} is newer than the latest release."  # noqa: E501
        if msg:
            gui.ToolTip(self.gui.update_lli_button, msg)
        self.clear_status()
        self.gui.update_lli_button.state([state])

    def update_latest_appimage_button(self, evt=None):
        state = None
        msg = None
        if not self.is_installed():
            state = "disabled"
            msg = "Please install first"
        elif self.conf._raw.wine_binary_code not in ["Recommended", "AppImage", None]:  # noqa: E501
            state = 'disabled'
            msg = "This button is disabled. The configured install was not created using an AppImage."  # noqa: E501
            self.gui.set_appimage_button.state(['disabled'])
            gui.ToolTip(
                self.gui.set_appimage_button,
                "This button is disabled. The configured install was not created using an AppImage."  # noqa: E501
            )
        elif self.conf._raw.wine_binary is not None:
            status, _ = utils.compare_recommended_appimage_version(self)
            if status == 0:
                state = '!disabled'
            elif status == 1:
                state = 'disabled'
                msg = "This button is disabled. The AppImage is already set to the latest recommended."  # noqa: E501
            elif status == 2:
                state = 'disabled'
                msg = "This button is disabled. The AppImage version is newer than the latest recommended."  # noqa: E501
            else:
                # Failed to check
                state = '!disabled'
        else:
            # Not enough context to figure out if this should be enabled or not
            state = '!disabled'
        if msg:
            gui.ToolTip(self.gui.latest_appimage_button, msg)
        self.clear_status()
        self.gui.latest_appimage_button.state([state])

    def _config_update_hook(self, evt=None):
        self.update_logging_button()
        self.update_app_button()
        try:
            self.update_latest_lli_release_button()
        except Exception:
            logging.exception("Failed to update release button")
        try:
            self.update_latest_appimage_button()
        except Exception:
            logging.exception("Failed to update appimage button")


    def current_logging_state_value(self) -> str:
        if self.conf.faithlife_product_logging:
            return 'ENABLED'
        else:
            return 'DISABLED'

    def reverse_logging_state_value(self, state) ->str:
        if state == 'DISABLED':
            return 'ENABLED'
        else:
            return 'DISABLED'


def set_style(tkapp):
    # Set the theme.
    tkapp.style = Style()
    tkapp.style.theme_use('alt')

    # Update color scheme.
    tkapp.style.configure('TCheckbutton', bordercolor=constants.LOGOS_GRAY)
    tkapp.style.configure('TCombobox', bordercolor=constants.LOGOS_GRAY)
    tkapp.style.configure('TCheckbutton', indicatorcolor=constants.LOGOS_GRAY)
    tkapp.style.configure('TRadiobutton', indicatorcolor=constants.LOGOS_GRAY)
    bg_widgets = [
        'TCheckbutton', 'TCombobox', 'TFrame', 'TLabel', 'TRadiobutton'
    ]
    fg_widgets = ['TButton', 'TSeparator']
    for w in bg_widgets:
        tkapp.style.configure(w, background=constants.LOGOS_WHITE)
    for w in fg_widgets:
        tkapp.style.configure(w, background=constants.LOGOS_GRAY)
    tkapp.style.configure(
        'Horizontal.TProgressbar',
        thickness=10, background=constants.LOGOS_BLUE,
        bordercolor=constants.LOGOS_GRAY,
        troughcolor=constants.LOGOS_GRAY,
    )

    # Justify to the left [('Button.label', {'sticky': 'w'})]
    tkapp.style.layout(
        "TButton", [(
            'Button.border', {
                'sticky': 'nswe', 'children': [(
                    'Button.focus', {
                        'sticky': 'nswe', 'children': [(
                            'Button.padding', {
                                'sticky': 'nswe', 'children': [(
                                    'Button.label', {'sticky': 'w'}
                                )]
                            }
                        )]
                    }
                )]
            }
        )]
    )


def start_gui_app(
    ephemeral_config: EphemeralConfiguration,
    recovery: Optional[Callable[[App], None]] = None,
    install_only: bool = False
):
    classname = constants.BINARY_NAME
    root = Root(className=classname)

    # Need to title/resize and create the initial gui
    # BEFORE mainloop is started to get sizing correct other things
    # in the ControlWindow constructor are run after mainloop is running
    # To allow them to ask questions while the mainloop is running
    root.title(f"{constants.APP_NAME} Control Panel")
    root.resizable(False, False)

    def _start_install() -> Callable[[], None]:
        # This needs to be created before root.mainloop is called
        installer_gui = gui.StatusWithLabelGui(root, "Installing FaithLife app")
        def _run():
            app = GuiApp(root, installer_gui, ephemeral_config)
            # This may take a minute to run, as it may need to reach out to the internet
            app.populate_defaults()
            installer.install(app)
            # Wait for a couple seconds so user can understand they're done.
            time.sleep(3)
            root.destroy()
        return _run

    def _start_control_panel() -> Callable[[], None]:
        # This needs to be created before root.mainloop is called
        control_gui = gui.ControlGui(root)
        def _run():
            if recovery:
                recovery_gui = gui.StatusWithLabelGui(root, "Recovering FaithLife app")
                recovery(GuiApp(root, recovery_gui, ephemeral_config))
                recovery_gui.destroy()
            ControlWindow(root, control_gui, ephemeral_config, class_=classname)
        return _run

    if install_only:
        target=_start_install()
    else:
        target=_start_control_panel()

    # Start the control panel on a new thread so it can open dialogs
    # as a part of it's constructor
    threading.Thread(
        name=f"{constants.APP_NAME} GUI main loop",
        target=target,
        daemon=True
    ).start()

    root.mainloop()
