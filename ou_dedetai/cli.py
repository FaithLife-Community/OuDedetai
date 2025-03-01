import queue
import shutil
import threading
import time
from typing import Optional, Tuple

from ou_dedetai import constants
from ou_dedetai.app import App
from ou_dedetai.config import EphemeralConfiguration
from ou_dedetai.system import SuperuserCommandNotFound
from ou_dedetai.logos import State as LogosRunningState

from . import control
from . import installer
from . import wine
from . import utils


class CLI(App):
    def __init__(self, ephemeral_config: EphemeralConfiguration):
        super().__init__(ephemeral_config)
        self.running: bool = True
        self.choice_q: queue.Queue[str] = queue.Queue()
        self.input_q: queue.Queue[Tuple[str, list[str]] | None] = queue.Queue()
        self.input_event = threading.Event()
        self.choice_event = threading.Event()
        self.start_thread(self.user_input_processor)

    def backup(self):
        control.backup(app=self)

    def create_shortcuts(self):
        installer.create_launcher_shortcuts(self)

    def edit_config(self):
        control.edit_file(self.conf.config_file_path)

    def install_app(self):
        installer.install(self)
        self.exit("Install has finished", intended=True)

    def install_dependencies(self):
        utils.install_dependencies(app=self)

    def install_icu(self):
        wine.enforce_icu_data_files(self)

    def remove_index_files(self):
        control.remove_all_index_files(self)

    def remove_install_dir(self):
        control.remove_install_dir(self)

    def remove_library_catalog(self):
        control.remove_library_catalog(self)

    def restore(self):
        control.restore(app=self)

    def run_indexing(self):
        self.logos.index()

    def run_installed_app(self):
        self.logos.start()
        # Keep the process running so that our background threads can keep running
        while self.logos.logos_state != LogosRunningState.STOPPED:
            time.sleep(3)
            self.logos.monitor()

    def stop_installed_app(self):
        self.logos.stop()

    def winetricks(self):
        wine.run_winetricks(self, *(self.conf._overrides.wine_args or []))

    def wine(self):
        wine.run_wine_proc(
            self.conf.wine64_binary,
            self,
            exe_args=(self.conf._overrides.wine_args or [])
        )

    def set_appimage(self):
        utils.set_appimage_symlink(app=self)

    def toggle_app_logging(self):
        self.logos.switch_logging()

    def update_latest_appimage(self):
        utils.update_to_latest_recommended_appimage(self)

    def update_self(self):
        utils.update_to_latest_lli_release(self)

    def get_support(self):
        control.get_support(self)

    _exit_option: str = "Exit"

    def _ask(self, question: str, options: list[str] | str) -> str:
        """Passes the user input to the user_input_processor thread
        
        The user_input_processor is running on the thread that the user's stdin/stdout
        is attached to. This function is being called from another thread so we need to
        pass the information between threads using a queue/event
        """
        if isinstance(options, str):
            options = [options]
        self.input_q.put((question, options))
        self.input_event.set()
        self.choice_event.wait()
        self.choice_event.clear()
        output: str = self.choice_q.get()
        # NOTE: this response is validated in App's .ask
        return output

    def exit(self, reason: str, intended: bool = False):
        # Signal CLI.user_input_processor to stop.
        self.input_q.put(None)
        self.input_event.set()
        # Signal CLI itself to stop.
        self.running = False
        # We always want this to return regardless of level
        print(f"Closing {constants.APP_NAME} due to: {reason}")
        return super().exit(reason, intended)
    
    def _status(self, message: str, percent: Optional[int] = None):
        """Implementation for updating status pre-front end"""
        prefix = ""
        end = "\n"
        # Signifies we want to overwrite the last line
        if message.endswith("\r"):
            end = "\r"
        if message == self._last_status:
            # Go back to the beginning of the line to re-write the current line
            # Rather than sending a new one. This allows the current line to update
            prefix += "\r"
            end = "\r"
        if percent is not None:
            percent_per_char = 5
            chars_of_progress = round(percent / percent_per_char)
            chars_remaining = round((100 - percent) / percent_per_char)
            progress_str = "[" + "-" * chars_of_progress + " " * chars_remaining + "] "
            prefix += progress_str
        print(f"{prefix}{message}", end=end)

    @property
    def superuser_command(self) -> str:
        if shutil.which('sudo'):
            return "sudo"
        else:
            raise SuperuserCommandNotFound("sudo command not found. Please install.")

    def user_input_processor(self, evt=None) -> None:
        while self.running:
            prompt = None
            question: Optional[str] = None
            options = None
            choice: Optional[str] = None
            # Wait for next input queue item.
            self.input_event.wait()
            self.input_event.clear()
            prompt = self.input_q.get()
            if prompt is None:
                return
            if prompt is not None and isinstance(prompt, tuple):
                question = prompt[0]
                options = prompt[1]
            if question is not None and options is not None:
                # Convert options list to string.
                default = options[0]
                optstr = f"{options[0]} [default], " + ', '.join(options[1:])
                choice = input(f"{question}: {optstr}: ")
                if len(choice) == 0:
                    choice = default
            if choice is not None and choice == self._exit_option:
                self.running = False
            if choice is not None:
                self.choice_q.put(choice)
                self.choice_event.set()
