import curses
import os
from pathlib import Path
import signal
import textwrap

from ou_dedetai import tui_screen
from ou_dedetai.app import App


def wrap_text(app: App, text: str) -> list[str]:
    from ou_dedetai.tui_app import TUI
    if not isinstance(app, TUI):
        raise ValueError("curses MUST be used with the TUI")
    # Turn text into wrapped text, line by line, centered
    column_margin = app.terminal_margin * 2
    column_width = app.window_width - column_margin
    if "\n" in text:
        lines = text.splitlines()
        wrapped_lines = [textwrap.fill(line, column_width).splitlines() for line in lines] 
        wrapped_text = [wrapped for sublist in wrapped_lines for wrapped in sublist]
    else:
        wrapped_text = textwrap.fill(text, column_width).splitlines()
    return wrapped_text


def write_line(app: App, stdscr: curses.window, start_y, start_x, text, char_limit, attributes=curses.A_NORMAL): 
    from ou_dedetai.tui_app import TUI
    if not isinstance(app, TUI):
        raise ValueError("curses MUST be used with the TUI")
    try:
        stdscr.addnstr(start_y, start_x, text, char_limit, attributes)
    except curses.error:
        # This may happen if we try to write beyond the screen limits
        # May happen when the window is resized before we've handled it
        pass


def title(app: App, stdscr: curses.window, title_text, title_start_y_adj):
    from ou_dedetai.tui_app import TUI
    if not isinstance(app, TUI):
        raise ValueError("curses MUST be used with the TUI")
    if not stdscr:
        raise Exception("Expected main window to be initialized, but it wasn't")
    title_lines = wrap_text(app, title_text)
    # title_start_y = max(0, app.window_height // 2 - len(title_lines) // 2)
    last_index = 0
    for i, line in enumerate(title_lines):
        if i < app.window_height:
            write_line(app, stdscr, i + title_start_y_adj, 2, line, app.window_width, curses.A_BOLD) 
        last_index = i

    return last_index


def text_centered(app: App, stdscr: curses.window, text: str, start_y=0) -> tuple[int, list[str]]:
    from ou_dedetai.tui_app import TUI
    if not isinstance(app, TUI):
        raise ValueError("curses MUST be used with the TUI")
    text_lines = wrap_text(app, text)
    text_start_y = start_y
    text_width = max(len(line) for line in text_lines)
    column_margin = app.terminal_margin * 2
    for i, line in enumerate(text_lines):
        if text_start_y + i < app.window_height:
            x = app.window_width // 2 - text_width // 2
            write_line(
                app,
                stdscr,
                text_start_y + i,
                max(column_margin, x),
                line,
                # column_margin is doubled to account for the left side's column_margin
                app.window_width - (column_margin * 2),
                curses.A_BOLD
            )

    return text_start_y, text_lines


def spinner(app: App, stdscr: curses.window, index: int, start_y: int = 0):
    spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧"]
    i = index
    text_centered(app, stdscr, spinner_chars[i], start_y)
    i = (i + 1) % len(spinner_chars)
    return i


#FIXME: Display flickers.
def confirm(app: App, question_text: str, height=None, width=None):
    from ou_dedetai.tui_app import TUI
    if not isinstance(app, TUI):
        raise ValueError("curses MUST be used with the TUI")
    stdscr = app.get_main_window()
    question_text = question_text + " [Y/n]: "
    question_start_y, question_lines = text_centered(app, stdscr, question_text)

    y = question_start_y + len(question_lines) + 2

    while True:
        key = stdscr.getch()
        key = chr(key)

        if key.lower() == 'y' or key == '\n':  # '\n' for Enter key, defaults to "Yes"
            return True
        elif key.lower() == 'n':
            return False

        write_line(app, stdscr, y, 0, "Type Y[es] or N[o]. ", app.window_width, curses.A_BOLD) 


class CursesDialog:
    def __init__(self, app):
        from ou_dedetai.tui_app import TUI
        self.app: TUI = app
        self.stdscr: curses.window = self.app.get_main_window()

    def __str__(self):
        return "Curses Dialog"

    def draw(self):
        pass

    def input(self):
        pass

    def run(self):
        pass


class UserInputDialog(CursesDialog):
    def __init__(self, app, question_text: str, default_text: str):
        super().__init__(app)
        self.question_text = question_text
        self.default_text = default_text
        self.user_input = default_text
        self.submit = False

        self.question_start_y, self.question_lines = text_centered(self.app, self.stdscr, self.question_text) 


    def __str__(self):
        return "UserInput Curses Dialog"

    def draw(self):
        curses.echo()
        curses.curs_set(1)
        self.stdscr.clear()
        self.question_start_y, self.question_lines = text_centered(self.app, self.stdscr, self.question_text) 
        self.input()
        curses.curs_set(0)
        curses.noecho()
        self.stdscr.refresh()

    @property
    def show_text(self) -> str:
        """Text to show to the user. Normally their input"""
        return self.user_input

    def input(self):
        write_line(
            self.app,
            self.stdscr,
            self.question_start_y + len(self.question_lines) + 2,
            10,
            self.show_text,
            self.app.window_width
        ) 
        key = self.stdscr.getch(self.question_start_y + len(self.question_lines) + 2, 10 + len(self.show_text)) 

        try:
            if key == -1:  # If key not found, keep processing.
                pass
            elif key == ord('\n'):  # Enter key
                self.submit = True
            elif key == curses.KEY_BACKSPACE or key == 127:
                if len(self.user_input) > 0:
                    self.user_input = self.user_input[:-1]
            elif key == 9: # Tab
                # Handle tab complete if the input is path life
                if self.user_input.startswith("~"):
                    self.user_input = os.path.expanduser(self.user_input)
                if self.user_input.startswith(os.path.sep):
                    path = Path(self.user_input)
                    dir_path = path.parent
                    if self.user_input.endswith(os.path.sep):
                        path_name = ""
                        dir_path = path
                    elif path.parent.exists():
                        path_name = path.name
                    if dir_path.exists():
                        options = os.listdir(dir_path)
                        options = [option for option in options if option.startswith(path_name)] 
                        # Displaying all these options may be complicated, for now for
                        # now only display if there is only one option
                        if len(options) == 1:
                            self.user_input = options[0]
                            if Path(self.user_input).is_dir():
                                self.user_input += os.path.sep
                        # Or see if all the options have the same prefix
                        common_chars = ""
                        for i in range(min([len(option) for option in options])):
                            # If all of the options are the same
                            if len(set([option[i] for option in options])) == 1:
                                common_chars += options[0][i]
                        if common_chars:
                            self.user_input = str(dir_path / common_chars)
            else:
                self.user_input += chr(key)
        except KeyboardInterrupt:
            signal.signal(signal.SIGINT, self.app.end)

    def run(self):
        if not self.submit:
            self.draw()
            return "Processing"
        else:
            if self.user_input is None or self.user_input == "":
                self.user_input = self.default_text
            return self.user_input


class PasswordDialog(UserInputDialog):
    @property
    def show_text(self) -> str:
        """Obfuscate the user's input"""
        return "*" * len(self.user_input)


class MenuDialog(CursesDialog):
    def __init__(self, app, question_text, options):
        super().__init__(app)
        self.user_input = "Processing"
        self.submit = False
        self.question_text = question_text
        self.app.options = options
        self.question_start_y = None
        self.question_lines = None

    def __str__(self):
        return "Menu Curses Dialog"

    def draw(self):
        self.stdscr.erase()
        # We should be on a menu screen at this point
        if isinstance(self.app.active_screen, tui_screen.MenuScreen):
            self.app.active_screen.set_options(self.app.options)
        self.app.total_pages = (len(self.app.options) - 1) // self.app.options_per_page + 1

        self.question_start_y, self.question_lines = text_centered(self.app, self.stdscr, self.question_text) 
        # Display the options, centered
        options_start_y = self.question_start_y + len(self.question_lines) + 1
        for i in range(self.app.options_per_page):
            index = self.app.current_page * self.app.options_per_page + i
            if index < len(self.app.options):
                option = self.app.options[index]
                if type(option) is list:
                    option_lines = []
                    wine_binary_code = option[0]
                    if wine_binary_code != "Exit":
                        wine_binary_path = option[1]
                        wine_binary_description = option[2]
                        wine_binary_path_wrapped = textwrap.wrap(
                            f"Binary Path: {wine_binary_path}", self.app.window_width - 4) 
                        option_lines.extend(wine_binary_path_wrapped)
                        wine_binary_desc_wrapped = textwrap.wrap(
                            f"Description: {wine_binary_description}", self.app.window_width - 4) 
                        option_lines.extend(wine_binary_desc_wrapped)
                    else:
                        wine_binary_path = option[1]
                        wine_binary_description = option[2]
                        wine_binary_path_wrapped = textwrap.wrap(
                            f"{wine_binary_path}", self.app.window_width - 4)
                        option_lines.extend(wine_binary_path_wrapped)
                        wine_binary_desc_wrapped = textwrap.wrap(
                            f"{wine_binary_description}", self.app.window_width - 4)
                        option_lines.extend(wine_binary_desc_wrapped)
                else:
                    option_lines = textwrap.wrap(option, self.app.window_width - 4)

                for j, line in enumerate(option_lines):
                    y = options_start_y + i + j
                    x = max(0, self.app.window_width // 2 - len(line) // 2)
                    if y < self.app.main_window_height:
                        if index == self.app.current_option:
                            write_line(self.app, self.stdscr, y, x, line, self.app.window_width, curses.A_REVERSE) 
                        else:
                            write_line(self.app, self.stdscr, y, x, line, self.app.window_width) 
                self.app.menu_bottom = y

                if type(option) is list:
                    options_start_y += (len(option_lines))

    def do_menu_up(self):
        if self.app.current_option == self.app.current_page * self.app.options_per_page and self.app.current_page > 0: 
            # Move to the previous page
            self.app.current_page -= 1
            self.app.current_option = min(
                len(self.app.menu_options) - 1, 
                (self.app.current_page + 1) * self.app.options_per_page - 1
            )
        elif self.app.current_option == 0:
            if self.app.total_pages == 1:
                self.app.current_option = len(self.app.menu_options) - 1
            else:
                self.app.current_page = self.app.total_pages - 1
                self.app.current_option = len(self.app.menu_options) - 1
        else:
            self.app.current_option = max(0, self.app.current_option - 1)

    def do_menu_down(self):
        if (
            self.app.current_option == (self.app.current_page + 1) * self.app.options_per_page - 1
            and self.app.current_page < self.app.total_pages - 1
        ): 
            # Move to the next page
            self.app.current_page += 1
            self.app.current_option = min(
                len(self.app.menu_options) - 1,
                self.app.current_page * self.app.options_per_page
            )
        elif self.app.current_option == len(self.app.menu_options) - 1:
            self.app.current_page = 0
            self.app.current_option = 0
        else:
            self.app.current_option = min(len(self.app.menu_options) - 1, self.app.current_option + 1) 

    def input(self):
        if len(self.app.tui_screens) > 0:
            self.stdscr = self.app.tui_screens[-1].get_stdscr()
        else:
            self.stdscr = self.app.main_screen.get_stdscr()
        key = self.stdscr.getch()

        try:
            if key == -1:  # If key not found, keep processing.
                pass
            elif key == curses.KEY_UP or key == 259 or key == curses.KEY_LEFT or key == 260:  # Up arrow
                self.do_menu_up()
            elif key == curses.KEY_DOWN or key == 258 or key == curses.KEY_RIGHT or key == 261:  # Down arrow
                self.do_menu_down()
            elif key == 27:
                # Sometimes the up/down arrow key is represented by a series of 3 keys.
                next_key = self.stdscr.getch()
                if next_key == 91:
                    final_key = self.stdscr.getch()
                    if final_key == 65:
                        self.do_menu_up()
                    elif final_key == 66:
                        self.do_menu_down()
            elif key == ord('\n') or key == 10:  # Enter key
                self.user_input = self.app.options[self.app.current_option]
            elif key == ord('\x1b'):
                signal.signal(signal.SIGINT, self.app.end)
        except KeyboardInterrupt:
            signal.signal(signal.SIGINT, self.app.end)

        self.stdscr.noutrefresh()

    def run(self):
        #thread = utils.start_thread(self.input, daemon_bool=False)
        #thread.join()
        self.draw()
        self.input()
        return self.user_input

    def set_options(self, new_options):
        self.app.options = new_options
        self.app.menu_options = new_options
