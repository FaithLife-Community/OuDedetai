import logging
import os
import signal
import sys
import threading
import time
import curses
from pathlib import Path
from queue import Queue
from typing import Any, Optional

from ou_dedetai.app import App, UserExitedFromAsk
from ou_dedetai.constants import (
    PROMPT_OPTION_DIRECTORY,
    PROMPT_OPTION_FILE
)
from ou_dedetai.config import EphemeralConfiguration

from . import control
from . import constants
from . import installer
from . import logos
from . import msg
from . import system
from . import tui_curses
from . import tui_screen
from . import utils
from . import wine

console_message = ""



# TODO: Fix hitting cancel in Dialog Screens; currently crashes program.
class TUI(App):
    def __init__(self, stdscr: curses.window, ephemeral_config: EphemeralConfiguration):
        super().__init__(ephemeral_config)
        self.stdscr = stdscr
        self.set_title()
        # else:
        #    self.title = f"Welcome to {constants.APP_NAME} ({constants.LLI_CURRENT_VERSION})"  # noqa: E501
        self.console_message = "Starting TUI…"
        self.is_running = True
        self.active_progress = False
        self.tmp = ""

        # Generic ask/response events/threads
        self.ask_answer_queue: Queue[str] = Queue()
        self.ask_answer_event = threading.Event()

        # Queues
        self.main_thread = threading.Thread()
        self.status_q: Queue[str] = Queue()
        self.status_e = threading.Event()
        self.todo_q: Queue[str] = Queue()
        self.todo_e = threading.Event()
        self.choice_q: Queue[str] = Queue()

        # Install and Options
        self.password_q: Queue[str] = Queue()
        self.password_e = threading.Event()
        self.appimage_q: Queue[str] = Queue()
        self.appimage_e = threading.Event()
        self._installer_thread: Optional[threading.Thread] = None

        self.terminal_margin = 2
        self.resizing = False
        # These two are updated in set_window_dimensions
        self.console_log_lines = 0
        self.options_per_page = 0

        # Window and Screen Management
        self.tui_screens: list[tui_screen.Screen] = []
        self.menu_options: list[Any] = []

        # Default height and width to something reasonable so these values are always
        # ints, on each loop these values will be updated to their real values
        self.window_height_min = 20
        self.window_height = self.window_width = 80
        self.header_window_height = self.header_window_width = 80
        self.console_window_height = self.console_window_width = 80
        self.main_window_height = self.main_window_width = 80
        self.footer_window_height = self.footer_window_width = 80
        # Default to a value to allow for int type
        self.header_window_height_min: int = 0
        self.console_window_height_min: int = 0
        self.main_window_height_min: int = 0
        self.footer_window_height_min: int = 0

        self.header_window_ratio: Optional[float] = None
        self.console_window_ratio: Optional[float] = None
        self.main_window_ratio: Optional[float] = None
        self.footer_window_ratio: Optional[float] = None
        self.header_window: Optional[curses.window] = None
        self.console_window: Optional[curses.window] = None
        self.main_window: Optional[curses.window] = None
        self.footer_window: Optional[curses.window] = None
        self.resize_window: Optional[curses.window] = None
        self.windows: list = []

        # For menu dialogs.
        # a new MenuDialog is created every loop, so we can't store it there.
        self.options: list = []
        self.current_option: int = 0
        self.current_page: int = 0
        self.total_pages: int = 0
        self.menu_bottom: int = 0

        # Start internal property variables, shouldn't be accessed directly, see their 
        # corresponding @property functions
        self._main_screen: Optional[tui_screen.MenuScreen] = None
        self._active_screen: Optional[tui_screen.Screen] = None
        self._header: Optional[tui_screen.ConsoleScreen] = None
        self._console: Optional[tui_screen.ConsoleScreen] = None
        self._footer: Optional[tui_screen.FooterScreen] = None
        # End internal property values

        # Lines for the on-screen console log
        self.console_log: list[str] = []

        # Turn off using python dialog for now, as it wasn't clear when it should have
        # been used before. And doesn't add value.
        # Before some function calls didn't pass use_python_dialog falling back to False
        # now it all respects use_python_dialog
        # some menus may open in dialog that didn't before.
        self.use_python_dialog: bool = False
        if "dialog" in sys.modules and ephemeral_config.terminal_app_prefer_dialog is not False: #noqa: E501
            result = system.test_dialog_version()

            if result is None:
                logging.debug(
                    "The 'dialog' package was not found. Falling back to Python Curses."
                )  # noqa: E501
            elif result:
                logging.debug("Dialog version is up-to-date.")
                self.use_python_dialog = True
            else:
                logging.error(
                    "Dialog version is outdated. The program will fall back to Curses."
                )  # noqa: E501
        # FIXME: remove this hard-coding after considering whether we want to continue 
        # to support both
        self.use_python_dialog = False

        logging.debug(f"Use Python Dialog?: {self.use_python_dialog}")
        self.create_windows()

        self.config_updated_hooks += [self._config_update_hook]

    def set_title(self):
        self.title = f"Welcome to {constants.APP_NAME} {constants.LLI_CURRENT_VERSION} ({self.conf.app_release_channel})"  # noqa: E501
        product_name = self.conf._raw.faithlife_product or constants.FAITHLIFE_PRODUCTS[0] #noqa: E501
        if self.is_installed():
            self.subtitle = f"{product_name} Version: {self.conf.installed_faithlife_product_release} ({self.conf.faithlife_product_release_channel})"  # noqa: E501
        else:
            self.subtitle = f"{product_name} not installed"
        # Reset the console to force a re-draw
        self._console = None

    @property
    def active_screen(self) -> tui_screen.Screen:
        if self._active_screen is None:
            self._active_screen = self.main_screen
            if self._active_screen is None:
                raise ValueError("Curses hasn't been initialized yet")
        return self._active_screen

    @active_screen.setter
    def active_screen(self, value: tui_screen.Screen):
        self._active_screen = value

    @property
    def main_screen(self) -> tui_screen.MenuScreen:
        if self._main_screen is None:
            self._main_screen = tui_screen.MenuScreen(
                self,
                0,
                self.status_q,
                self.status_e,
                "Main Menu",
                self.set_tui_menu_options(),
            )  # noqa: E501
        return self._main_screen
    
    @property
    def console(self) -> tui_screen.ConsoleScreen:
        if self._console is None:
            self._console = tui_screen.ConsoleScreen(
                self, 0, self.status_q, self.status_e, 0
            )  # noqa: E501
        return self._console

    @property
    def header(self) -> tui_screen.HeaderScreen:
        if self._header is None:
            self._header = tui_screen.HeaderScreen(
                self, 0, self.status_q, self.status_e, self.title, self.subtitle, 0
            )  # noqa: E501
        return self._header

    @property
    def footer(self) -> tui_screen.FooterScreen:
        if self._footer is None:
            self._footer = tui_screen.FooterScreen(
                self, 0, self.status_q, self.status_e, 0
            )  # noqa: E501
        return self._footer

    @property
    def recent_console_log(self) -> list[str]:
        """Outputs console log trimmed by the maximum length"""
        return self.console_log[-self.console_log_lines:]

    def set_header_window_dimensions(self):
        self.header_window_height_min = 2
        self.header_window_height = min(max(
            int(self.window_height * self.header_window_ratio), self.header_window_height_min
        ), 4)

    def set_console_window_dimensions(self):
        if self.console_log:
            min_console_height = len(tui_curses.wrap_text(self, self.console_log[-1]))
        else:
            min_console_height = 2
        self.header_window_height_min = (
            len(tui_curses.wrap_text(self, self.title))
            + len(tui_curses.wrap_text(self, self.subtitle))
            + min_console_height
        )
        self.console_window_height = max(
            int(self.window_height * self.console_window_ratio), self.console_window_height_min
        )  # noqa: E501
        self.console_log_lines = max(self.console_window_height - self.console_window_height_min, 1)

    def set_footer_window_dimensions(self):
        self.footer_window_height_min = 3
        self.footer_window_height = 3
        #self.footer_window_height = max(
        #    int(self.window_height * self.footer_window_ratio), self.footer_window_height_min
        #)

    def set_main_window_dimensions(self):
        self.main_window_height_min = 5
        self.main_window_height = max(
            int(self.window_height * self.main_window_ratio), self.main_window_height_min,
        )  # noqa: E501

    def set_window_dimensions(self):
        curses.resizeterm(self.window_height, self.window_width)
        self.header_window_ratio = 0.10
        self.console_window_ratio = 0.15
        self.footer_window_ratio = 0.10
        self.main_window_ratio = 0.55  # Intentionally short his by 10% to avoid hidden lines

        self.set_header_window_dimensions()
        self.set_console_window_dimensions()
        self.set_footer_window_dimensions()
        self.set_main_window_dimensions()

    def set_windows(self):
        self.options_per_page = max(self.window_height - self.header_window_height - self.console_window_height - self.main_window_height_min - self.footer_window_height, 1)

        header_window_start = 0
        console_window_start = self.header_window_height
        main_window_start = self.header_window_height + self.console_window_height + 1
        footer_window_start = self.header_window_height + self.console_window_height + self.main_window_height + 2

        self.header_window = curses.newwin(self.header_window_height, curses.COLS, header_window_start, 0)
        self.console_window = curses.newwin(self.console_window_height, curses.COLS, console_window_start, 0)
        self.main_window = curses.newwin(self.main_window_height, curses.COLS, main_window_start, 0)
        self.footer_window = curses.newwin(self.footer_window_height, curses.COLS, footer_window_start, 0)

        resize_lines = tui_curses.wrap_text(self, "Screen too small.")
        self.resize_window = curses.newwin(len(resize_lines) + 1, curses.COLS, 0, 0)

        self.windows = [self.header_window, self.console_window, self.main_window,
                        self.footer_window]

    def create_windows(self):
        self.update_tty_dimensions()
        self.set_window_dimensions()
        self.set_windows()

    @staticmethod
    def set_curses_style():
        curses.start_color()
        curses.use_default_colors()
        curses.init_color(curses.COLOR_BLUE, 0, 510, 1000)  # Logos Blue
        curses.init_color(curses.COLOR_CYAN, 906, 906, 906)  # Logos Gray
        curses.init_color(curses.COLOR_WHITE, 988, 988, 988)  # Logos White
        curses.init_pair(1, -1, -1)  # System
        curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_WHITE)
        curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLUE)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Logos
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Light
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Dark

    def set_background_color(self, color_pair_option):
        self.stdscr.bkgd(" ", curses.color_pair(color_pair_option))
        for i in self.windows:
            if i:
                i.bkgd(" ", curses.color_pair(color_pair_option))

    def set_curses_color_scheme(self):
        if self.conf.curses_color_scheme == "System":
            self.set_background_color(1)
        elif self.conf.curses_color_scheme == "Logos":
            self.set_background_color(4)
        elif self.conf.curses_color_scheme == "Light":
            self.set_background_color(6)
        elif self.conf.curses_color_scheme == "Dark":
            self.set_background_color(7)

    def erase(self):
        for i in self.windows:
            if i:
                i.erase()

    def clear(self):
        self.stdscr.clear()
        for i in self.windows:
            if i:
                i.clear()

    def refresh(self):
        self.stdscr.timeout(100)
        for i in self.windows:
            if i:
                i.noutrefresh()
        curses.doupdate()

    def init_curses(self):
        try:
            if curses.has_colors():
                self.set_curses_style()
                self.set_curses_color_scheme()

            curses.curs_set(0)
            curses.noecho()
            curses.cbreak()
            self.stdscr.keypad(True)

            # Reset console/main_screen. They'll be initialized next access
            self._header = None
            self._console = None
            self._main_screen = tui_screen.MenuScreen(
                self,
                0,
                self.status_q,
                self.status_e,
                "Main Menu",
                self.set_tui_menu_options(),
            )  # noqa: E501
            self._footer = None
            # self.main_screen = tui_screen.MenuDialog(self, 0, self.status_q, self.status_e, "Main Menu", self.set_tui_menu_options(dialog=True)) #noqa: E501
            self.refresh()
        except curses.error as e:
            logging.error(f"Curses error in init_curses: {e}")
        except Exception as e:
            self.end_curses()
            logging.error(f"An error occurred in init_curses(): {e}")
            raise

    def end_curses(self):
        try:
            self.stdscr.keypad(False)
            curses.nocbreak()
            curses.echo()
        except curses.error as e:
            logging.error(f"Curses error in end_curses: {e}")
            raise
        except Exception as e:
            logging.error(f"An error occurred in end_curses(): {e}")
            raise

    def _exit(self, reason, intended = False):
        message = f"Exiting {constants.APP_NAME} due to {reason}…"
        if not intended:
            message += "\n" + constants.SUPPORT_MESSAGE
        self._status(message)
        time.sleep(30)
        self.end(None, None)

    def end(self, signal, frame):
        logging.debug("Exiting…")
        self.is_running = False
        curses.endwin()

    def update_main_window_contents(self):
        self.main_screen.set_options(self.set_tui_menu_options())

    # ERR: On a sudden resize, the Curses menu is not properly resized,
    # and we are not currently dynamically passing the menu options based
    # on the current screen, but rather always passing the tui menu options.
    # To replicate, open Terminator, run LLI full screen, then his Ctrl+A.
    # The menu should survive, but the size does not resize to the new screen,
    # even though the resize signal is sent. See tui_curses, line #251 and
    # tui_screen, line #98.
    def resize_curses(self):
        self.resizing = True
        curses.endwin()
        self.create_windows()
        self.clear()
        self.init_curses()
        self.refresh()
        logging.debug("Window resized.")
        self.resizing = False

    def signal_resize(self, signum, frame):
        self.resize_curses()
        self.choice_q.put("resize")

        if self.use_python_dialog:
            if (
                isinstance(self.active_screen, tui_screen.TextDialog)
                and self.active_screen.text == "Screen Too Small"
            ):
                self.choice_q.put("Return to Main Menu")

    def draw_resize_screen(self):
        self.clear()
        if self.window_width > self.window_height_min:
            margin = self.terminal_margin
        else:
            margin = 0
        resize_lines = tui_curses.wrap_text(self, "Screen too small.")
        self.resize_window = curses.newwin(len(resize_lines) + 1, curses.COLS, 0, 0)
        self.windows = [self.resize_window]
        for i, line in enumerate(resize_lines):
            if i < self.window_height:
                tui_curses.write_line(
                    self,
                    self.resize_window,
                    i,
                    margin,
                    line,
                    self.window_width - self.terminal_margin,
                    curses.A_BOLD,
                )
        self.refresh()

    def display(self):
        signal.signal(signal.SIGWINCH, self.signal_resize)
        signal.signal(signal.SIGINT, self.end)
        msg.initialize_tui_logging()

        # Makes sure status stays shown
        timestamp = utils.get_timestamp()
        self.status_q.put(f"{timestamp} {self.console_message}")
        self.report_waiting(f"{self.console_message}")  # noqa: E501

        self.active_screen = self.main_screen
        check_resize_last_time = last_time = time.time()

        while self.is_running:
            if self.window_height >= self.window_height_min and self.window_width >= 35:
                self.terminal_margin = 2
                if not self.resizing:
                    if isinstance(self.active_screen, tui_screen.CursesScreen):
                        self.erase()
                        self.header.display()
                        self.console.display()
                        self.footer.display()

                    self.active_screen.display()

                    if self.choice_q.qsize() > 0:
                        self.choice_processor(
                            self.main_window,
                            self.active_screen.screen_id,
                            self.choice_q.get(),
                        )
                        if self.active_screen.screen_id == 2:
                            if self.tui_screens:
                                self.tui_screens.pop()

                    if len(self.tui_screens) == 0:
                        self.active_screen = self.main_screen
                    else:
                        self.active_screen = self.tui_screens[-1]

                    if not isinstance(self.active_screen, tui_screen.DialogScreen):
                        run_monitor, last_time = utils.stopwatch(last_time, 2.5)
                        if run_monitor:
                            self.logos.monitor()
                            self.main_screen.set_options(self.set_tui_menu_options())

                    if isinstance(self.active_screen, tui_screen.CursesScreen):
                        self.refresh()
            elif self.window_width >= self.window_height_min:
                if self.window_width < self.window_height_min:
                    # Avoid drawing errors on very small screens
                    self.terminal_margin = 1
                self.draw_resize_screen()
            elif self.window_width < self.window_height_min:
                self.terminal_margin = 0  # Avoid drawing errors on very small screens
            # Check every second to see if the screen resized without our know-how
            # This is done on a timer because curses.is_term_resized takes a fair bit of
            # time for this loop
            # If flashing is observed on a screen, it's possible this timer needs to be 
            # increased
            check_resize, check_resize_last_time = utils.stopwatch(check_resize_last_time, 1) #noqa: E501
            if check_resize and curses.is_term_resized(self.window_height, self.window_width): #noqa: E501
                # The screen has changed sizes since we last checked. Resize
                self.resize_curses()

    def run(self):
        try:
            self.init_curses()
            self.display()
        except KeyboardInterrupt:
            self.end_curses()
            signal.signal(signal.SIGINT, self.end)
        finally:
            self.end_curses()
            signal.signal(signal.SIGINT, self.end)

    def installing_pw_waiting(self):
        # self.start_thread(self.get_waiting, screen_id=15)
        pass

    def choice_processor(self, stdscr, screen_id, choice):
        screen_actions = {
            0: self.main_menu_select,
            1: self.custom_appimage_select,
            2: self.handle_ask_response,
            8: self.waiting,
            10: self.waiting_releases,
            11: self.wineconfig_menu_select,
            12: self.logos.start,
            13: self.waiting_finish,
            15: self.password_prompt,
            18: self.utilities_menu_select,
            19: self.renderer_select,
            20: self.win_ver_logos_select,
            21: self.win_ver_index_select,
            24: self.confirm_restore_dir,
            25: self.choose_restore_dir,
        }

        # Capture menu exiting before processing in the rest of the handler
        if screen_id not in [0, 2] and (choice in ["Return to Main Menu", "Exit"]):
            if choice == "Return to Main Menu":
                self.tui_screens = []
            self.reset_screen()
            # FIXME: There is some kind of graphical glitch that activates on returning
            # to Main Menu, but not from all submenus.
            # Further, there appear to be issues with how the program exits on Ctrl+C as
            # part of this.
        else:
            action = screen_actions.get(screen_id)
            if action:
                # Start the action in a new thread to not interrupt the input thread
                self.start_thread(
                    action,
                    choice,
                    daemon_bool=False,
                )
            else:
                pass

    def reset_screen(self):
        self.active_screen.running = 0
        self.active_screen.choice = "Processing"
        self.current_option = 0
        self.current_page = 0
        self.total_pages = 0

    def go_to_main_menu(self):
        self.tui_screens = []
        self.reset_screen()
        self.main_screen.choice = "Processing"
        # Reset running state of main menu so it can submit again.
        self.main_screen.running = 0
        self.choice_q.put("Return to Main Menu")

    def main_menu_select(self, choice):
        def _install():
            try:
                installer.install(app=self)
            except UserExitedFromAsk:
                pass
            finally:
                self.go_to_main_menu()

        if choice is None or choice == "Exit":
            logging.info("Exiting installation.")
            self.tui_screens = []
            self.is_running = False

        if choice in ["Install", "Advanced Install"]:
            if self._installer_thread is not None:
                # The install thread should have completed with UserExitedFromAsk
                # Check just in case
                if self._installer_thread.is_alive():
                    raise RuntimeError("Previous install is still running")

            self.reset_screen()
            self.installer_step = 0
            self.installer_step_count = 0

            if choice.startswith("Install"):
                logging.debug(f"{self.conf.faithlife_product=}")
                self.conf._overrides.assume_yes = True
            elif choice.startswith("Advanced"):
                pass  # Stub

            self._installer_thread = self.start_thread(
                _install,
                daemon_bool=True,
            )
        elif choice.startswith(f"Update {constants.APP_NAME}"):
            utils.update_to_latest_lli_release(self)
        elif self.conf._raw.faithlife_product and choice == f"Run {self.conf._raw.faithlife_product}": #noqa: E501
            self.reset_screen()
            self.logos.start()
            self.main_screen.set_options(self.set_tui_menu_options())
        elif self.conf._raw.faithlife_product and choice == f"Stop {self.conf.faithlife_product}": #noqa: E501
            self.reset_screen()
            self.logos.stop()
            self.main_screen.set_options(self.set_tui_menu_options())
        elif choice == "Run Indexing":
            self.active_screen.running = 0
            self.active_screen.choice = "Processing"
            self.logos.index()
        elif choice == "Remove Library Catalog":
            self.active_screen.running = 0
            self.active_screen.choice = "Processing"
            control.remove_library_catalog(self)
        elif choice.startswith("Wine Config"):
            self.reset_screen()
            self.stack_menu(
                11,
                self.todo_q,
                self.todo_e,
                "Wine Config Menu",
                self.set_wineconfig_menu_options(),
            )
        elif choice.startswith("Utilities"):
            self.reset_screen()
            self.stack_menu(
                18,
                self.todo_q,
                self.todo_e,
                "Utilities Menu",
                self.set_utilities_menu_options(),
            )
        elif choice == "Change Color Scheme":
            self.status("Changing color scheme")
            self.conf.cycle_curses_color_scheme()
            self.go_to_main_menu()
        elif choice == "Get Support":
            control.get_support(self)
            self.go_to_main_menu()

    def wineconfig_menu_select(self, choice):
        if choice == "Set Renderer":
            self.reset_screen()
            self.stack_menu(
                19,
                self.todo_q,
                self.todo_e,
                "Choose Renderer",
                self.set_renderer_menu_options(),
            )
            self.choice_q.put("0")
        elif choice == "Set Windows Version for Logos":
            self.reset_screen()
            self.stack_menu(
                20,
                self.todo_q,
                self.todo_e,
                "Set Windows Version for Logos",
                self.set_win_ver_menu_options(),
            )
            self.choice_q.put("0")
        elif choice == "Set Windows Version for Indexer":
            self.reset_screen()
            self.stack_menu(
                21,
                self.todo_q,
                self.todo_e,
                "Set Windows Version for Indexer",
                self.set_win_ver_menu_options(),
            )
            self.choice_q.put("0")

    def utilities_menu_select(self, choice):
        if choice == "Remove Library Catalog":
            self.reset_screen()
            control.remove_library_catalog(self)
            self.go_to_main_menu()
        elif choice == "Remove All Index Files":
            self.reset_screen()
            control.remove_all_index_files(self)
            self.go_to_main_menu()
        elif choice == "Edit Config":
            self.reset_screen()
            control.edit_file(self.conf.config_file_path)
            self.go_to_main_menu()
        elif choice == "Reload Config":
            self.conf.reload()
            self.go_to_main_menu()
        elif choice == "Change Logos Release Channel":
            self.reset_screen()
            self.conf.toggle_faithlife_product_release_channel()
            self.go_to_main_menu()
        elif choice == f"Change {constants.APP_NAME} Release Channel":
            self.reset_screen()
            self.conf.toggle_installer_release_channel()
            self.go_to_main_menu()
        elif choice == "Install Dependencies":
            self.reset_screen()
            utils.install_dependencies(self)
            self.go_to_main_menu()
        elif choice == "Back Up Data":
            self.reset_screen()
            self.start_thread(self.do_backup)
        elif choice == "Restore Data":
            self.reset_screen()
            self.start_thread(self.do_backup)
        elif choice == "Update to Latest AppImage":
            self.reset_screen()
            utils.update_to_latest_recommended_appimage(self)
            self.go_to_main_menu()
        # This isn't an option in set_utilities_menu_options
        # This code path isn't reachable and isn't tested post-refactor
        elif choice == "Set AppImage":
            # TODO: Allow specifying the AppImage File
            appimages = self.conf.wine_app_image_files
            appimage_choices = appimages
            appimage_choices.extend(["Input Custom AppImage", "Return to Main Menu"])
            self.menu_options = appimage_choices
            question = "Which AppImage should be used?"
            self.stack_menu(
                1, self.appimage_q, self.appimage_e, question, appimage_choices
            )
        elif choice == "Install ICU":
            self.reset_screen()
            wine.enforce_icu_data_files(self)
            self.go_to_main_menu()
        elif choice.endswith("Logging"):
            self.reset_screen()
            self.logos.switch_logging()
            self.go_to_main_menu()

    def custom_appimage_select(self, choice: str):
        if choice == "Input Custom AppImage":
            appimage_filename = self.ask("Enter AppImage filename: ", [PROMPT_OPTION_FILE]) #noqa: E501
        else:
            appimage_filename = choice
        self.conf.wine_appimage_path = Path(appimage_filename)
        utils.set_appimage_symlink(self)
        if not self.main_window:
            raise ValueError("Curses hasn't been initialized")
        self.main_screen.choice = "Processing"
        self.appimage_q.put(str(self.conf.wine_appimage_path))
        self.appimage_e.set()

    def waiting(self, choice):
        pass

    def waiting_releases(self, choice):
        pass

    def waiting_finish(self, choice):
        pass

    def waiting_resize(self, choice):
        pass

    def password_prompt(self, choice):
        if choice:
            self.main_screen.choice = "Processing"
            self.password_q.put(choice)
            self.password_e.set()

    def renderer_select(self, choice):
        if choice in ["gdi", "gl", "vulkan"]:
            self.reset_screen()
            self.status(f"Changing renderer to {choice}.", 0)
            wine.set_renderer(self, self.conf.wine64_binary, choice)
            self.status(f"Changed renderer to {choice}.", 100)
            self.go_to_main_menu()

    def win_ver_logos_select(self, choice):
        if choice in ["vista", "win7", "win8", "win10", "win11"]:
            self.reset_screen()
            self.status(f"Changing Windows version for Logos to {choice}.", 0)
            wine.set_win_version(self, "logos", choice)
            self.status(f"Changed Windows version for Logos to {choice}.", 100)
            self.go_to_main_menu()

    def win_ver_index_select(self, choice):
        if choice in ["vista", "win7", "win8", "win10", "win11"]:
            self.reset_screen()
            self.status(f"Changing Windows version for Indexer to {choice}.", 0)
            wine.set_win_version(self, "indexer", choice)
            self.status(f"Changed Windows version for Indexer to {choice}.", 100)
            self.go_to_main_menu()

    def switch_screen(self):
        if (
            self.active_screen is not None
            and self.active_screen != self.main_screen
            and len(self.tui_screens) > 0
        ):  # noqa: E501
            self.tui_screens.pop(0)
        if self.active_screen == self.main_screen:
            self.main_screen.choice = "Processing"
            self.main_screen.running = 0
        if isinstance(self.active_screen, tui_screen.CursesScreen):
            self.clear()

    _exit_option = "Return to Main Menu"

    def _ask(self, question: str, options: list[str] | str) -> Optional[str]:
        self.ask_answer_event.clear()
        if isinstance(options, str):
            answer = options
        elif isinstance(options, list):
            self.menu_options = self.which_dialog_options(options)
            self.stack_menu(
                2, Queue(), threading.Event(), question, self.menu_options
            )

            # Now wait for it to complete.
            self.ask_answer_event.wait()
            answer = self.ask_answer_queue.get()

        self.ask_answer_event.clear()
        if answer in constants.PROMPT_OPTION_SIGILS:
            self.stack_input(
                2,
                Queue(),
                threading.Event(),
                question,
                os.path.expanduser("~/"),
            )
            # Now wait for it to complete
            self.ask_answer_event.wait()
            new_answer = self.ask_answer_queue.get()
            if answer == PROMPT_OPTION_DIRECTORY:
                # Make the directory if it doesn't exit.
                # form a terminal UI, it's not easy for the user to manually
                os.makedirs(new_answer, exist_ok=True)

            answer = new_answer

        if answer == self._exit_option:
            self.tui_screens = []
            self.reset_screen()

        return answer

    def handle_ask_response(self, choice: str):
        self.ask_answer_queue.put(choice)
        self.ask_answer_event.set()

    def _info(self, message: str) -> None:
        """Display information to the user"""
        self.ask_answer_event.clear()
        self.stack_menu(
            2,
            Queue(),
            threading.Event(),
            message,
            self.which_dialog_options(['Return to Main Menu']),
        )

        # Wait for user response.
        self.ask_answer_event.wait()
        _ = self.ask_answer_queue.get()
        self.ask_answer_event.clear()

    def _status(self, message: str, percent: int | None = None):
        message = message.lstrip("\r")
        if self.console_log[-1] == message:
            return
        self.console_log.append(message)
        self.stack_text(
            8,
            self.status_q,
            self.status_e,
            message,
            wait=True,
            percent=percent or 0,
        )

    def _config_update_hook(self):
        self.update_main_window_contents()
        self.set_curses_color_scheme()
        self.set_title()

    # def get_password(self, dialog):
    #     question = (f"Logos Linux Installer needs to run a command as root. "
    #                 f"Please provide your password to provide escalation privileges.")
    #     self.screen_q.put(self.stack_password(15, self.password_q, self.password_e, question, dialog=dialog)) #noqa: E501

    def confirm_restore_dir(self, choice):
        if choice:
            if choice == "Yes":
                self.tmp = "Yes"
            else:
                self.tmp = "No"
            self.todo_e.set()

    def choose_restore_dir(self, choice):
        if choice:
            self.tmp = choice
            self.todo_e.set()

    def do_backup(self):
        self.todo_e.wait()
        self.todo_e.clear()
        if self.tmp == "backup":
            control.backup(self)
        else:
            control.restore(self)
        self.go_to_main_menu()

    def report_waiting(self, text):
        # self.screen_q.put(self.stack_text(10, self.status_q, self.status_e, text, wait=True, dialog=dialog)) #noqa: E501
        self.console_log.append(text)

    def which_dialog_options(self, labels: list[str]) -> list[Any]: #noqa: E501
        # curses - list[str]
        # dialog - list[tuple[str, str]] 
        options: list[Any] = []
        option_number = 1
        for label in labels:
            if self.use_python_dialog:
                options.append((str(option_number), label))
                option_number += 1
            else:
                options.append(label)
        return options

    def set_tui_menu_options(self):
        labels = []
        if constants.RUNMODE == "binary":
            status = utils.compare_logos_linux_installer_version(self)
            if status == utils.VersionComparison.OUT_OF_DATE:
                labels.append(f"Update {constants.APP_NAME}")
            elif status == utils.VersionComparison.UP_TO_DATE:
                # logging.debug("Logos Linux Installer is up-to-date.")
                pass
            elif status == utils.VersionComparison.DEVELOPMENT:
                # logging.debug("Logos Linux Installer is newer than the latest release.")  # noqa: E501
                pass
            else:
                logging.error(f"Unknown result: {status}")

        if self.is_installed():
            if self.logos.logos_state in [logos.State.STARTING, logos.State.RUNNING]:  # noqa: E501
                run = f"Stop {self.conf.faithlife_product}"
            elif self.logos.logos_state in [logos.State.STOPPING, logos.State.STOPPED]:  # noqa: E501
                run = f"Run {self.conf.faithlife_product}"

            if self.logos.indexing_state == logos.State.RUNNING:
                indexing = "Stop Indexing"
            elif self.logos.indexing_state == logos.State.STOPPED:
                indexing = "Run Indexing"
            labels_default = [run, indexing]
        else:
            labels_default = ["Install", "Advanced Install"]
        labels.extend(labels_default)

        labels_support = ["Utilities →", "Wine Config →"]
        labels.extend(labels_support)

        labels_options = ["Change Color Scheme", "Get Support"]
        labels.extend(labels_options)

        labels.append("Exit")

        options = self.which_dialog_options(labels)

        return options

    def set_wineconfig_menu_options(self):
        labels = []
        labels_support = [
            "Set Renderer",
            "Set Windows Version for Logos",
            "Set Windows Version for Indexer",
        ]
        labels.extend(labels_support)

        labels.append("Return to Main Menu")

        options = self.which_dialog_options(labels)

        return options

    def set_renderer_menu_options(self):
        labels = []
        labels_support = ["gdi", "gl", "vulkan"]
        labels.extend(labels_support)

        labels.append("Return to Main Menu")

        options = self.which_dialog_options(labels)

        return options

    def set_win_ver_menu_options(self):
        labels = []
        labels_support = ["vista", "win7", "win8", "win10", "win11"]
        labels.extend(labels_support)

        labels.append("Return to Main Menu")

        options = self.which_dialog_options(labels)

        return options

    def set_utilities_menu_options(self):
        labels = []
        if self.is_installed():
            labels_catalog = [
                "Remove Library Catalog",
                "Remove All Index Files",
                "Install ICU",
            ]
            labels.extend(labels_catalog)

        labels_utilities = ["Install Dependencies", "Edit Config", "Reload Config"]
        labels.extend(labels_utilities)

        if self.is_installed():
            labels_utils_installed = [
                "Change Logos Release Channel",
                f"Change {constants.APP_NAME} Release Channel",
                # "Back Up Data",
                # "Restore Data"
            ]
            labels.extend(labels_utils_installed)

        label = (
            "Enable Logging"
            if self.conf.faithlife_product_logging
            else "Disable Logging"
        )  # noqa: E501
        labels.append(label)

        labels.append("Return to Main Menu")

        options = self.which_dialog_options(labels)

        return options

    def stack_menu(
        self,
        screen_id,
        queue,
        event,
        question,
        options,
        height=None,
        width=None,
        menu_height=8,
    ):  # noqa: E501
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.MenuDialog(
                    self,
                    screen_id,
                    queue,
                    event,
                    question,
                    options,
                    height,
                    width,
                    menu_height,
                ),
            )  # noqa: E501
        else:
            utils.append_unique(
                self.tui_screens,
                tui_screen.MenuScreen(
                    self,
                    screen_id,
                    queue,
                    event,
                    question,
                    options,
                    height,
                    width,
                    menu_height,
                ),
            )  # noqa: E501

    def stack_input(self, screen_id, queue, event, question: str, default):
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.InputDialog(
                    self, screen_id, queue, event, question, default
                ),
            )  # noqa: E501
        else:
            utils.append_unique(
                self.tui_screens,
                tui_screen.InputScreen(
                    self, screen_id, queue, event, question, default
                ),
            )  # noqa: E501

    def stack_password(
        self, screen_id, queue, event, question, default=""
    ):  # noqa: E501
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.PasswordDialog(
                    self, screen_id, queue, event, question, default
                ),
            )  # noqa: E501
        else:
            utils.append_unique(
                self.tui_screens,
                tui_screen.PasswordScreen(
                    self, screen_id, queue, event, question, default
                ),
            )  # noqa: E501

    def stack_confirm(
        self,
        screen_id,
        queue,
        event,
        question,
        no_text,
        secondary,
        options=["Yes", "No"],
    ):  # noqa: E501
        if self.use_python_dialog:
            yes_label = options[0]
            no_label = options[1]
            utils.append_unique(
                self.tui_screens,
                tui_screen.ConfirmDialog(
                    self,
                    screen_id,
                    queue,
                    event,
                    question,
                    no_text,
                    secondary,
                    yes_label=yes_label,
                    no_label=no_label,
                ),
            )  # noqa: E501
        else:
            utils.append_unique(
                self.tui_screens,
                tui_screen.ConfirmScreen(
                    self, screen_id, queue, event, question, no_text, secondary, options
                ),
            )  # noqa: E501

    def stack_text(
        self, screen_id, queue, event, text, wait=False, percent=None
    ):  # noqa: E501
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.TextDialog(
                    self, screen_id, queue, event, text, wait, percent
                ),
            )  # noqa: E501
        else:
            utils.append_unique(
                self.tui_screens,
                tui_screen.TextScreen(self, screen_id, queue, event, text, wait),
            )  # noqa: E501

    def stack_tasklist(
        self, screen_id, queue, event, text, elements, percent
    ):  # noqa: E501
        logging.debug(f"Elements stacked: {elements}")
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.TaskListDialog(
                    self, screen_id, queue, event, text, elements, percent
                ),
            )  # noqa: E501
        else:
            # TODO: curses version
            pass

    def stack_buildlist(
        self,
        screen_id,
        queue,
        event,
        question,
        options,
        height=None,
        width=None,
        list_height=None,
    ):  # noqa: E501
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.BuildListDialog(
                    self,
                    screen_id,
                    queue,
                    event,
                    question,
                    options,
                    height,
                    width,
                    list_height,
                ),
            )  # noqa: E501
        else:
            # TODO
            pass

    def stack_checklist(
        self,
        screen_id,
        queue,
        event,
        question,
        options,
        height=None,
        width=None,
        list_height=None,
    ):
        if self.use_python_dialog:
            utils.append_unique(
                self.tui_screens,
                tui_screen.CheckListDialog(
                    self,
                    screen_id,
                    queue,
                    event,
                    question,
                    options,
                    height,
                    width,
                    list_height,
                ),
            )  # noqa: E501
        else:
            # TODO
            pass

    def update_tty_dimensions(self):
        self.window_height, self.window_width = self.stdscr.getmaxyx()

    def get_main_window(self):
        return self.main_window


def control_panel_app(stdscr: curses.window, ephemeral_config: EphemeralConfiguration):
    os.environ.setdefault("ESCDELAY", "100")
    TUI(stdscr, ephemeral_config).run()
