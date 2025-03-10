
import abc
import logging
import os
from pathlib import Path
import sys
import threading
from typing import Callable, NoReturn, Optional

from ou_dedetai import constants
from ou_dedetai.constants import (
    PROMPT_OPTION_DIRECTORY,
    PROMPT_OPTION_FILE,
    PROMPT_OPTION_NEW_FILE
)


class UserExitedFromAsk(Exception):
    """Exception thrown when the user hit cancel in an ask dialog"""


class App(abc.ABC):
    # FIXME: consider weighting install steps. Different steps take different lengths
    installer_step_count: int = 0
    """Total steps in the installer, only set the installation process has started."""
    installer_step: int = 1
    """Step the installer is on. Starts at 0"""

    _threads: list[threading.Thread]
    """List of threads
    
    Non-daemon threads will be joined before shutdown
    """
    _last_status: Optional[str] = None
    """The last status we had"""
    config_updated_hooks: list[Callable[[], None]] = []
    _config_updated_event: threading.Event = threading.Event()

    def __init__(self, config, **kwargs) -> None:
        # This lazy load is required otherwise these would be circular imports
        from ou_dedetai.config import Config
        from ou_dedetai.logos import LogosManager
        from ou_dedetai.system import check_incompatibilities

        self.conf = Config(config, self)
        self.logos = LogosManager(app=self)
        self._threads = []
        # Ensure everything is good to start
        check_incompatibilities(self)

        def _config_updated_hook_runner():
            while True:
                self._config_updated_event.wait()
                self._config_updated_event.clear()
                for hook in self.config_updated_hooks:
                    try:
                        hook()
                    except Exception:
                        logging.exception("Failed to run config update hook")
        _config_updated_hook_runner.__name__ = "Config Update Hook"
        self.start_thread(_config_updated_hook_runner, daemon_bool=True)

    def ask(self, question: str, options: list[str]) -> str:
        """Asks the user a question with a list of supplied options

        Returns the option the user picked.

        If the internal ask function returns None, the process will exit with 1
        """
        def validate_result(answer: str, options: list[str]) -> Optional[str]:
            special_cases = set(constants.PROMPT_OPTION_SIGILS)
            # These constants have special meaning, don't worry about them to start with
            simple_options = list(set(options) - special_cases)
            # This MUST have the same indexes as above
            simple_options_lower = [opt.lower() for opt in simple_options]

            # Case sensitive check first
            if answer in simple_options:
                return answer
            # Also do a case insensitive match, no reason to fail due to casing
            if answer.lower() in simple_options_lower:
                # Return the correct casing to simplify the parsing of the ask result
                return simple_options[simple_options.index(answer.lower())]
            
            # Now check the special cases
            if PROMPT_OPTION_FILE in options and Path(answer).is_file():
                return answer
            if PROMPT_OPTION_DIRECTORY in options and Path(answer).is_dir():
                return answer
            if (
                PROMPT_OPTION_NEW_FILE in options
                and not Path(answer).is_dir()
                and Path(answer).parent.is_dir()
            ):
                return answer

            # Not valid
            return None

        # Check to see if we're supposed to prompt the user
        if self.conf._overrides.assume_yes:
            # Get the first non-dynamic option
            for option in options:
                if option not in [PROMPT_OPTION_DIRECTORY, PROMPT_OPTION_FILE]:
                    return option

        passed_options: list[str] | str = options
        if len(passed_options) == 1 and passed_options[0] in constants.PROMPT_OPTION_SIGILS: #noqa: E501
            # Set the only option to be the follow up prompt
            passed_options = options[0]
        elif passed_options is not None and self._exit_option is not None:
            passed_options = options + [self._exit_option]

        answer = self._ask(question, passed_options)
        if answer is None or answer == self._exit_option:
            raise UserExitedFromAsk
        while answer is None or validate_result(answer, options) is None:
            invalid_response = "That response is not valid, please try again."
            new_question = f"{invalid_response}\n{question}"
            answer = self._ask(new_question, passed_options)

        if answer is not None:
            answer = validate_result(answer, options)
            if answer is None:
                # Huh? coding error, this should have been checked earlier
                logging.critical("An invalid response slipped by, please report this incident to the developers") #noqa: E501
                self.exit("Failed to get a valid value from user")

        return answer

    def approve_or_exit(self, question: str, context: Optional[str] = None) -> bool:
        """Asks the user a question, if they refuse, shutdown"""
        if not self.approve(question, context):
            self.exit(f"User refused the prompt: {question}")
        return True

    def approve(self, question: str, context: Optional[str] = None) -> bool:
        """Asks the user a y/n question"""
        question = (f"{context}\n\n" if context else "") + question
        options = ["Yes", "No"]
        return self.ask(question, options) == "Yes"

    def info(self, message: str, context: Optional[str] = None) -> None:
        """Shares information with the user"""
        message = (f"{context}\n" if context else "") + message
        self._info(message)

    def _exit(self, reason: str, intended: bool = False) -> None:
        """Cleanup any lingering objects, per-implementation specific"""

    def exit(self, reason: str, intended: bool = False) -> NoReturn:
        """Exits the application cleanly with a reason."""
        logging.debug(f"Closing {constants.APP_NAME}.")
        self._exit(reason, intended)
        # Shutdown logos/indexer if we spawned it
        self.logos.end_processes()
        # Join threads
        for thread in self._threads:
            # Only wait on non-daemon threads.
            if not thread.daemon:
                try:
                    thread.join()
                except RuntimeError:
                    # Will happen if we try to join the current thread
                    pass
        # Remove pid file if exists
        try:
            os.remove(constants.PID_FILE)
        except FileNotFoundError:  # no pid file when testing functions
            pass
        # exit from the process
        if intended:
            sys.exit(0)
        else:
            logging.critical(f"Cannot continue because {reason}\n{constants.SUPPORT_MESSAGE}") #noqa: E501
            sys.exit(1)

    _exit_option: Optional[str] = "Exit"

    @abc.abstractmethod
    def _ask(self, question: str, options: list[str] | str) -> Optional[str]:
        """Implementation for asking a question per-front end

        Options may include ability to prompt for an additional value.
        Such as asking for one of strings or a directory.
        If the user selects choose a new directory, the
        implementations MUST handle the follow up prompt before returning

        Options may be a single value,
        Implementations MUST handle this single option being a follow up prompt
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _info(self, message: str) -> None:
        """Implementation for displaying information to the user per-front end
        """
        raise NotImplementedError()

    def is_installed(self) -> bool:
        """Returns whether the install was successful by
        checking if the installed exe exists and is executable"""
        if self.conf.logos_exe is not None:
            return os.access(self.conf.logos_exe, os.X_OK)
        return False

    def status(self, message: str, percent: Optional[int | float] = None):
        """A status update
        
        Args:
            message: str - if it ends with a \r that signifies that this message is
                intended to be overrighten next time
            percent: Optional[int] - percent of the way through the current install step
                (if installing)
        """
        # Check to see if we want to suppress all output
        if self.conf._overrides.quiet:
            return

        if isinstance(percent, float):
            percent = round(percent * 100)
        # If we're installing
        if self.installer_step_count != 0:
            current_step_percent = percent or 0
            # We're further than the start of our current step, percent more
            installer_percent = round((self.installer_step * 100 + current_step_percent) / self.installer_step_count) # noqa: E501
            logging.debug(f"Install {installer_percent}%: {message}")
            self._status(message, percent=installer_percent)
        else:
            # Otherwise just print status using the progress given
            logging.debug(f"{message}: {percent}%")
            self._status(message, percent)
        self._last_status = message

    @abc.abstractmethod
    def _status(self, message: str, percent: Optional[int] = None):
        """Implementation for updating status pre-front end
        
        Args:
            message: str - if it ends with a \r that signifies that this message is
                intended to be overridden next time
            percent: Optional[int] - percent complete of the current overall operation
                if None that signifies we can't track the progress.
                Feel free to implement a spinner
        """

        def get_progressbar(pct, w=10, suffix=''):
            suffix = f" {int(pct):>3}%"
            # end = '\r'

            ci = '\u23b8'
            cf = '\u23b9'
            d = '█'
            u = ' '
            d_ct = min(int(w*pct/100), w)
            u_ct = min(int(w - d_ct - 1), w - 1)

            bar = ''
            if d_ct == 0:
                bar += ci + u*(u_ct - 1) + cf
            elif d_ct < w:
                bar += str(d*d_ct) + str(u*u_ct) + cf
            else:
                bar += str(d*d_ct)
            bar += suffix #+ end
            return bar

        # De-dup
        if message != self._last_status:
            bar = ''
            if percent is not None:
                bar = f"{get_progressbar(percent)}"
            if message.endswith("\r"):
                print(f"{bar}{message}", end="\r")
            else:
                print(f"{message}")
                if bar:
                    print(bar)
        

    @property
    def superuser_command(self) -> str:
        """Command when root privileges are needed.

        Raises:
            SuperuserCommandNotFound

        May be sudo or pkexec for example"""
        from ou_dedetai.system import get_superuser_command
        return get_superuser_command()

    def start_thread(self, task, *args, daemon_bool: bool = True, **kwargs):
        """Starts a new thread
        
        Non-daemon threads be joined before shutdown"""
        thread = threading.Thread(
            name=f"{constants.APP_NAME} {task}",
            target=task,
            daemon=daemon_bool,
            args=args,
            kwargs=kwargs
        )
        self._threads.append(thread)
        thread.start()
        return thread