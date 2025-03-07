import curses
import logging
import time
from queue import Queue
from threading import Event
from typing import Optional

from . import installer
from . import system
from . import tui_curses
if system.have_dep("dialog"):
    from . import tui_dialog

from ou_dedetai.app import App

class Screen:
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event):
        from ou_dedetai.tui_app import TUI
        if not isinstance(app, TUI):
            raise ValueError("Cannot start TUI screen with non-TUI app")
        self.app: TUI = app
        self.stdscr: Optional[curses.window] = None
        self.screen_id = screen_id
        self.choice = "Processing"
        self.queue = queue
        self.event = event
        # running:
        # This var indicates either whether:
        # A CursesScreen has already submitted its choice to the choice_q, or
        # The var indicates whether a Dialog has already started. If the dialog has already started, #noqa: E501
        # then the program will not display the dialog again in order to prevent phantom key presses. #noqa: E501
        # 0 = not submitted or not started
        # 1 = submitted or started
        # 2 = none or finished
        self.running = 0

    def __str__(self):
        return "Curses Screen"

    def display(self):
        pass

    def get_stdscr(self) -> curses.window:
        return self.app.stdscr

    def wait_event(self):
        self.event.wait()

    def is_set(self):
        return self.event.is_set()


class CursesScreen(Screen):
    def submit_choice_to_queue(self):
        if self.running == 0 and self.choice != "Processing":
            self.app.choice_q.put(self.choice)
            self.running = 1


class DialogScreen(Screen):
    def submit_choice_to_queue(self):
        if self.running == 1 and self.choice != "Processing":
            self.app.choice_q.put(self.choice)
            self.running = 2


class ConsoleScreen(CursesScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, start_y: int):
        super().__init__(app, screen_id, queue, event)
        self.stdscr: Optional[curses.window] = self.app.console_window
        self.start_y = start_y

    def __str__(self):
        return "Curses Console Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the console screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        tui_curses.write_line(self.app, self.stdscr, self.start_y, self.app.terminal_margin, "---Console---", self.app.window_width - (self.app.terminal_margin * 2)) #noqa: E501
        recent_messages = self.app.recent_console_log
        for i, message in enumerate(recent_messages, 1):
            message_lines = tui_curses.wrap_text(self.app, message)
            for j, line in enumerate(message_lines):
                if 2 + j < self.app.window_height:
                    truncated = message[:self.app.window_width - (self.app.terminal_margin * 2)] #noqa: E501
                    tui_curses.write_line(self.app, self.stdscr, self.start_y + i, self.app.terminal_margin, truncated, self.app.window_width - (self.app.terminal_margin * 2)) #noqa: E501

        self.stdscr.noutrefresh()
        curses.doupdate()


class HeaderScreen(CursesScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, title: str, subtitle: str, title_start_y: int):
        super().__init__(app, screen_id, queue, event)
        self.stdscr: Optional[curses.window] = self.app.header_window
        self.title = title
        self.subtitle = subtitle
        self.title_start_y = title_start_y

    def __str__(self):
        return "Curses Header Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the header screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        subtitle_start = tui_curses.title(self.app, self.stdscr, self.title, self.title_start_y)
        tui_curses.title(self.app, self.stdscr, self.subtitle, subtitle_start + 1)

        self.stdscr.noutrefresh()
        curses.doupdate()


class FooterScreen(CursesScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, start_y: int):
        super().__init__(app, screen_id, queue, event)
        self.stdscr: Optional[curses.window] = self.app.footer_window
        self.start_y = start_y

    def __str__(self):
        return "Curses Footer Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the footer screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()

        footer_text = "By the FaithLife Community"

        if isinstance(self.app.active_screen, MenuScreen):
            page_info = f"Page {self.app.current_page + 1}/{self.app.total_pages} | Selected Option: {self.app.current_option + 1}/{len(self.app.options)}" #noqa: E501
            tui_curses.write_line(self.app, self.stdscr, self.start_y, 2, page_info, self.app.window_width, curses.A_BOLD) #noqa: E501
        tui_curses.write_line(self.app, self.stdscr, self.app.footer_window_height - 1, self.app.terminal_margin, footer_text, self.app.window_width - (self.app.terminal_margin * 2)) #noqa: E501

        self.stdscr.noutrefresh()
        curses.doupdate()


class MenuScreen(CursesScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, question: str, options: list, height: int=None, width: int=None, menu_height: int=8): #noqa: E501
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.options = options
        self.height = height
        self.width = width
        self.menu_height = menu_height

    def __str__(self):
        return "Curses Menu Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the console screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        self.choice = tui_curses.MenuDialog(
            self.app,
            self.question,
            self.options
        ).run()
        if self.choice is not None and not self.choice == "" and not self.choice == "Processing": #noqa: E501
            self.submit_choice_to_queue()
        self.stdscr.noutrefresh()
        curses.doupdate()

    def get_question(self):
        return self.question

    def set_options(self, new_options):
        self.options = new_options
        self.app.menu_options = new_options


class ConfirmScreen(MenuScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, question: str, no_text: str, secondary: str, options: list=["Yes", "No"]): #noqa: E501
        super().__init__(app, screen_id, queue, event, question, options,
                         height=None, width=None, menu_height=8)
        self.no_text = no_text
        self.secondary = secondary

    def __str__(self):
        return "Curses Confirm Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the console screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        self.choice = tui_curses.MenuDialog(
            self.app,
            self.secondary + "\n" + self.question,
            self.options
        ).run()
        if self.choice is not None and not self.choice == "" and not self.choice == "Processing": #noqa: E501
            if self.choice == "No":
                logging.critical(self.no_text)
            self.submit_choice_to_queue()
        self.stdscr.noutrefresh()
        curses.doupdate()


class InputScreen(CursesScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, question: str, default: str):
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.default = default
        self.dialog = tui_curses.UserInputDialog(
            self.app,
            self.question,
            self.default
        )

    def __str__(self):
        return "Curses Input Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the console screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        self.choice = self.dialog.run()
        if not self.choice == "Processing":
            self.submit_choice_to_queue()
        self.stdscr.noutrefresh()
        curses.doupdate()

    def get_question(self):
        return self.question

    def get_default(self):
        return self.default


class PasswordScreen(InputScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, question: str, default: str):
        super().__init__(app, screen_id, queue, event, question, default)
        # Update type for type linting
        from ou_dedetai.tui_app import TUI
        self.app: TUI = app
        self.dialog = tui_curses.PasswordDialog(
            self.app,
            self.question,
            self.default
        )

    def __str__(self):
        return "Curses Password Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the console screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        self.choice = self.dialog.run()
        if not self.choice == "Processing":
            self.submit_choice_to_queue()
            self.app.installing_pw_waiting()
        self.stdscr.noutrefresh()
        curses.doupdate()


class TextScreen(CursesScreen):
    def __init__(self, app: App, screen_id: int, queue: Queue, event: Event, text: str, wait: bool):
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.text = text
        self.wait = wait
        self.spinner_index = 0

    def __str__(self):
        return "Curses Text Screen"

    def display(self):
        if self.stdscr is None:
            raise Exception("stdscr should be set at this point in the console screen."
                            "Please report this incident to the developers")
        self.stdscr.erase()
        text_start_y, text_lines = tui_curses.text_centered(self.app, self.stdscr, self.text)
        if self.wait:
            self.spinner_index = tui_curses.spinner(self.app, self.stdscr, self.spinner_index, text_start_y + len(text_lines) + 1) #noqa: E501
            time.sleep(0.1)
        self.stdscr.noutrefresh()
        curses.doupdate()

    def get_text(self):
        return self.text


class MenuDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, question, options, height=None, width=None, menu_height=8): #noqa: E501
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.options = options
        self.height = height
        self.width = width
        self.menu_height = menu_height

    def __str__(self):
        return "PyDialog Menu Screen"

    def display(self):
        if self.running == 0:
            self.running = 1
            _, _, self.choice = tui_dialog.menu(self.app, self.question, self.options, 
                                                self.height, self.width, 
                                                self.menu_height)
            self.submit_choice_to_queue()

    def get_question(self):
        return self.question

    def set_options(self, new_options):
        self.options = new_options


class InputDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, question, default):
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.default = default

    def __str__(self):
        return "PyDialog Input Screen"

    def display(self):
        if self.running == 0:
            self.running = 1
            choice = tui_dialog.directory_picker(self.app, self.default)
            if choice:
                self.choice = choice
            self.submit_choice_to_queue()

    def get_question(self):
        return self.question

    def get_default(self):
        return self.default


class PasswordDialog(InputDialog):
    def __init__(self, app, screen_id, queue, event, question, default):
        super().__init__(app, screen_id, queue, event, question, default)
        from ou_dedetai.tui_app import TUI
        self.app: TUI = app

    def __str__(self):
        return "PyDialog Password Screen"

    def display(self):
        if self.running == 0:
            self.running = 1
            _, self.choice = tui_dialog.password(self.app, self.question, init=self.default) #noqa: E501
            self.submit_choice_to_queue()
            self.app.installing_pw_waiting()


class ConfirmDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, question, no_text, secondary, yes_label="Yes", no_label="No"): #noqa: E501
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.no_text = no_text
        self.secondary = secondary
        self.yes_label = yes_label
        self.no_label = no_label

    def __str__(self):
        return "PyDialog Confirm Screen"

    def display(self):
        if self.running == 0:
            self.running = 1
            self.choice = tui_dialog.confirm(self.app, self.secondary + self.question,
                                                   self.yes_label, self.no_label)
            if self.choice == "cancel":
                self.choice = self.no_label
                logging.critical(self.no_text)
            else:
                self.choice = self.yes_label
            self.submit_choice_to_queue()

    def get_question(self):
        return self.question


class TextDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, text, wait=False, percent=None, 
                 height=None, width=None, title=None, backtitle=None, colors=True):
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.text = text
        self.percent = percent
        self.wait = wait
        self.height = height
        self.width = width
        self.title = title
        self.backtitle = backtitle
        self.colors = colors
        self.lastpercent = 0
        self.dialog = ""

    def __str__(self):
        return "PyDialog Text Screen"

    def display(self):
        if self.running == 0:
            if self.wait:
                if self.app.installer_step_count > 0:
                    self.percent = installer.get_progress_pct(self.app.installer_step, self.app.installer_step_count) #noqa: E501
                else:
                    self.percent = 0

                tui_dialog.progress_bar(self, self.text, self.percent)
                self.lastpercent = self.percent
            else:
                tui_dialog.text(self, self.text)
            self.running = 1
        elif self.running == 1:
            if self.wait:
                if self.app.installer_step_count > 0:
                    self.percent = installer.get_progress_pct(self.app.installer_step, self.app.installer_step_count) #noqa: E501
                else:
                    self.percent = 0

                if self.lastpercent != self.percent:
                    self.lastpercent = self.percent
                    tui_dialog.update_progress_bar(self, self.percent, self.text, True)
                    #tui_dialog.progress_bar(self, self.text, self.percent)

                if self.percent == 100:
                    tui_dialog.stop_progress_bar(self)
                    self.running = 2
                    self.wait = False

    def get_text(self):
        return self.text


class TaskListDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, text, elements, percent,
                 height=None, width=None, title=None, backtitle=None, colors=True):
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.text = text
        self.elements = elements if elements is not None else {}
        self.percent = percent
        self.height = height
        self.width = width
        self.title = title
        self.backtitle = backtitle
        self.colors = colors
        self.updated = False

    def __str__(self):
        return "PyDialog Task List Screen"

    def display(self):
        if self.running == 0:
            tui_dialog.tasklist_progress_bar(self, self.text, self.percent, 
                                             self.elements, self.height, self.width,
                                             self.title, self.backtitle, self.colors)
            self.running = 1
        elif self.running == 1:
            if self.updated:
                tui_dialog.tasklist_progress_bar(self, self.text, self.percent,
                                                 self.elements, self.height, self.width,
                                                 self.title, self.backtitle, 
                                                 self.colors)
        else:
            pass

        time.sleep(0.1)

    def set_text(self, text):
        self.text = text
        self.updated = True

    def set_percent(self, percent):
        self.percent = percent
        self.updated = True

    def set_elements(self, elements):
        self.elements = elements
        self.updated = True


class BuildListDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, question, options, list_height=None, height=None, width=None): #noqa: E501
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.options = options
        self.height = height
        self.width = width
        self.list_height = list_height

    def __str__(self):
        return "PyDialog Build List Screen"

    def display(self):
        if self.running == 0:
            self.running = 1
            code, self.choice = tui_dialog.buildlist(self.app, self.question, 
                                                     self.options, self.height, 
                                                     self.width, self.list_height)
            self.running = 2

    def get_question(self):
        return self.question

    def set_options(self, new_options):
        self.options = new_options


class CheckListDialog(DialogScreen):
    def __init__(self, app, screen_id, queue, event, question, options, list_height=None, height=None, width=None): #noqa: E501
        super().__init__(app, screen_id, queue, event)
        self.stdscr = self.app.get_main_window()
        self.question = question
        self.options = options
        self.height = height
        self.width = width
        self.list_height = list_height

    def __str__(self):
        return "PyDialog Check List Screen"

    def display(self):
        if self.running == 0:
            self.running = 1
            code, self.choice = tui_dialog.checklist(self.app, self.question, 
                                                     self.options, self.height, 
                                                     self.width, self.list_height)
            self.running = 2

    def set_options(self, new_options):
        self.options = new_options
