"""Basic implementations of some rudimentary tests

Should be migrated into unittests once that branch is merged
"""
# FIXME: refactor into unittests

import abc
import os
from pathlib import Path
import psutil
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable, Optional, Union

REPOSITORY_ROOT_PATH = Path(__file__).parent.parent

class CommandFailedError(Exception):
    """Command Failed to execute"""
    cmd_args: list[str]
    stdout: str
    stderr: str

    def __init__(self, args: list[str], stdout: str, stderr: str):
        self.cmd_args = args
        self.stdout = stdout
        self.stderr = stderr
        return super().__init__((
            f"Failed to execute: {" ".join(args)}:\n\n"
            f"stdout:\n{stdout}\n\n"
            f"stderr:\n{stderr}\n\n"
            "Command Failed. See above for details."
        ))

class MissingSystemBinary(Exception):
    """Failed to find a binary needed to run tests"""
    def __init__(self, command: str):
        super().__init__((
            "Failed to find command: "
            + command
            + "Please find and install it via your package manager."
        ))


class TestFailed(Exception):
    pass

def run_cmd(*args, **kwargs) -> subprocess.CompletedProcess[str]:
    """Wrapper around subprocess.run that:
    - captures stdin/stderr
    - sets text mode
    - checks returncode before returning

    All other args are passed through to subprocess.run
    """
    if "stdout" not in kwargs:
        kwargs["stdout"] = subprocess.PIPE
    if "stderr" not in kwargs:
        kwargs["stderr"] = subprocess.PIPE
    kwargs["text"] = True
    output = subprocess.run(*args, **kwargs)
    try:
        output.check_returncode()
    except subprocess.CalledProcessError as e:
        raise CommandFailedError(
            args=list(*args),
            stderr=output.stderr,
            stdout=output.stdout
        ) from e
    return output

class OuDedetai:
    _binary: Optional[str] = None
    _temp_dir: Optional[str] = None
    config: Optional[Path] = None
    install_dir: Optional[Path] = None
    log_level: str
    """Log level. One of:
    - quiet - warn+ - status
    - normal - warn+
    - verbose - info+
    - debug - debug
    """


    def __init__(self, isolate: bool = True, log_level: str = "quiet"):
        if isolate:
            self.isolate_files()
        self.log_level = log_level

    def isolate_files(self):
        if self._temp_dir is not None:
            shutil.rmtree(self._temp_dir)
        # XXX: this isn't properly cleaned up. Context manager?
        self._temp_dir = tempfile.mkdtemp()
        self.config = Path(self._temp_dir) / "config.json"
        self.install_dir = Path(self._temp_dir) / "install_dir"

    @classmethod
    def _source_last_update(cls) -> float:
        """Last updated time of any source code in seconds since epoch"""
        path = REPOSITORY_ROOT_PATH / "ou_dedetai"
        output: float = 0
        for root, _, files in os.walk(path):
            for file in files:
                file_m = os.stat(Path(root) / file).st_mtime
                if file_m > output:
                    output = file_m
        return output

    @classmethod
    def _oudedetai_binary(cls) -> str:
        """Return the path to the binary"""
        output = REPOSITORY_ROOT_PATH / "dist" / "oudedetai"
        # First check to see if we need to build.
        # If either the file doesn't exist, or it was last modified earlier than
        # the source code, rebuild.
        if (
            not output.exists()
            or cls._source_last_update() > os.stat(str(output)).st_mtime
        ):
            print("Building binary…")
            if output.exists():
                os.remove(str(output))
            run_cmd(f"{REPOSITORY_ROOT_PATH / "scripts" / "build-binary.sh"}")

            if not output.exists():
                raise Exception("Build process failed to yield binary")
            print("Built binary.")

        return str(output)

    def run(self, *args, **kwargs):
        if self._binary is None:
            self._binary = self._oudedetai_binary()
        if "env" not in kwargs:
            kwargs["env"] = {}
        env: dict[str, str] = {}
        if self.config:
            env["CONFIG_FILE"] = str(self.config)
        if self.install_dir:
            env["INSTALLDIR"] = str(self.install_dir)
        env["PATH"] = os.environ.get("PATH", "")
        env["HOME"] = os.environ.get("HOME", "")
        env["DISPLAY"] = os.environ.get("DISPLAY", "")
        kwargs["env"] = env
        log_level = ""
        if self.log_level == "debug":
            log_level = "--debug"
        elif self.log_level == "verbose":
            log_level = "--verbose"
        elif self.log_level == "quiet":
            log_level = "--quiet"
        args = ([self._binary, log_level, "--i-agree-to-faithlife-terms"] + args[0], *args[1:]) #noqa: E501
        # FIXME: Output to both stdout and PIPE (for debugging these tests)
        output = run_cmd(*args, **kwargs)

        # FIXME: Test to make sure there is no stderr output either - AKA no warnings
        # if output.stderr:
        #     raise CommandFailedError(
        #         args[0],
        #         stdout=output.stdout,
        #         stderr=output.stderr
        #     )
        return output

    def uninstall(self):
        try:
            self.stop_app()
        except Exception:
            pass
        # XXX: Ideally the uninstall operation would automatically stop the app.
        # Open an issue for this.
        self.run(["--uninstall", "-y"])

    def start_app(self) -> "Logos":
        # Start a thread, as this command doesn't exit
        threading.Thread(target=self.run, args=[["--run-installed-app"]]).start()
        # There is only one thing we need to check generally for logos.
        # Consider making display_server a paramater in the future if
        # this needs to be something else.
        display_server = DisplayServer.detect(raise_if_winedbg_is_running)
        logos = Logos(self, display_server)
        # Now wait for the window to open before returning the open window.
        wait_for_true(logos.is_window_open)
        display_server.window_name = logos.window_name()
        # Wait for a bit to ensure the Logos window is actually open
        time.sleep(20)
        return logos

    def stop_app(self):
        self.run(["--stop-installed-app"])
        # FIXME: wait for close?


# XXX: test this against Verbum too. It should be the same.
# If not, make this an abstract class w/overrides.

class Logos:
    """Class for interacting with Logos
    
    May also work for Verbum, tested against Logos"""
    _ou_dedetai: OuDedetai
    _display_server: "DisplayServer"

    def __init__(self, ou_dedetai: OuDedetai, display_server: "DisplayServer"):
        self._ou_dedetai = ou_dedetai
        self._display_server = display_server

    def run_command_box(self, command: str):
        """Given an open Logos, hit the required keys
        to execute in the command box
        """
        self._display_server.press_keys([
            KeyCodeEscape(),
            KeyCodeModified(KeyCodeAlt(), KeyCodeCharacter("c"))
        ])
        time.sleep(2)
        self._display_server.type_string(command)
        time.sleep(8)
        self._display_server.press_keys(KeyCodeReturn())
        time.sleep(10)

    def open_guide(self, guide: str):
        """Given an open Logos, hit the required keys
        to open a guide
        """
        self._display_server.press_keys([
            KeyCodeEscape(),
            KeyCodeModified(KeyCodeAlt(), KeyCodeCharacter("g"))
        ])
        time.sleep(2)
        self._display_server.type_string(guide)
        time.sleep(3)
        self._display_server.press_keys([KeyCodeTab(), KeyCodeReturn()])
        time.sleep(5)

    def open_tool(self, guide: str):
        """Given an open Logos, hit the required keys
        to open a tool
        """
        self._display_server.press_keys([
            KeyCodeEscape(),
            KeyCodeModified(KeyCodeAlt(), KeyCodeCharacter("t"))
        ])
        time.sleep(2)
        self._display_server.type_string(guide)
        time.sleep(4)
        self._display_server.press_keys([
            KeyCodeTab(),
            KeyCodeTab(),
            KeyCodeReturn(),
        ])
        time.sleep(4)

    def type_string(self, string: str):
        """Types string
        
        Calls pre_input_tasks before running"""
        self._display_server.type_string(string)

    def press_keys(self, keys: Union["KeyCode", list["KeyCode"]]):
        """Presses key(s)
        
        Calls pre_input_tasks before running"""
        self._display_server.press_keys(keys)
    
    def is_window_open(self) -> bool:
        """Checks to see if logos is open"""
        return self._display_server.is_window_open(self.window_name())

    def close(self):
        """Close Logos"""
        self._ou_dedetai.stop_app()

    def is_crashed(self) -> bool:
        """Checks to see if Logos crashed by:
        
        - If the window is closed
        - winedbg process is running
        """
        if is_winedbg_is_running():
            return True
        if not self.is_window_open():
            return True
        return False
    
    @classmethod
    def window_name(_cls):
        # FIXME: This will need to be overridden for Verbum
        return "Logos Bible Study"

def wait_for_true(
    callable: Callable[[], Optional[bool]],
    timeout: Optional[int] = 10,
    period: float = .1
) -> bool:
    exception = None
    start_time = time.time()
    while timeout is None or time.time() - start_time < timeout:
        try:
            if callable():
                return True
        except Exception as e:
            exception = e
        time.sleep(period)
    if exception:
        raise exception
    raise TimeoutError

class KeyCode(abc.ABC):
    """Display Server Independent KeyCode
    
    Purpose of this class is two-fold:
    - Display server independent
    - Preventing casing errors - ex. alt is lowercase on X11 and Return is capital
    """

    @abc.abstractmethod
    def x11_code(self) -> str:
        """Returns representation in X11"""
        raise NotImplementedError

    # FIXME: Will need to add a second one if/when wayland support is added to this test
    # suite.

class KeyCodeModifier(KeyCode):
    """KeyCode that specifically a modifier"""

class KeyCodeModified(KeyCode):
    """Keypress that's modified by some number of modifiers"""
    modifiers: list[KeyCodeModifier]
    key: KeyCode

    def __init__(
        self,
        modifiers: KeyCodeModifier | list[KeyCodeModifier],
        key: KeyCode
    ):
        if isinstance(modifiers, KeyCode):
            self.modifiers = [modifiers]
        else:
            self.modifiers = modifiers
        self.key = key

    def x11_code(self):
        return "+".join(
            [key.x11_code() for key in self.modifiers] 
            + [self.key.x11_code()]
        )

class KeyCodeCharacter(KeyCode):
    """Key code that's just a character"""
    char: str
    """Character. Stored as a string with length of one"""

    def __init__(self, char: str):
        if len(char) != 1:
            raise ValueError("Expected Key to be one character")
        self.char = char
    
    def x11_code(self):
        return self.char

class KeyCodeReturn(KeyCode):
    """Return Key"""

    def x11_code(self):
        return "Return"

class KeyCodeTab(KeyCode):
    """Tab Key"""

    def x11_code(self):
        return "Tab"

class KeyCodeAlt(KeyCodeModifier):
    """Alt Key"""

    def x11_code(self):
        return "alt"

class KeyCodeShift(KeyCodeModifier):
    """Shift Key"""

    def x11_code(self):
        return "shift"

class KeyCodeCtrl(KeyCodeModifier):
    """Ctrl Key"""

    def x11_code(self):
        return "ctrl"

class KeyCodeSpace(KeyCode):
    """Space Key"""

    def x11_code(self):
        return "space"

class KeyCodeEscape(KeyCode):
    """Escape Key"""

    def x11_code(self):
        return "Escape"

class DisplayServer(abc.ABC):
    """Abstract class for a display server. Like Xorg or Wayland"""

    pre_input_tasks: Callable[[], None]
    """Tasks to run before sending user input.
    
    Some things like error dialogs may be dismissed if we interact with the screen
    check these things before continuing.
    """
    window_name: Optional[str]
    """Window name to scope requests to"""

    def __init__(
        self,
        pre_input_tasks: Callable[[], None]
    ):
        self.pre_input_tasks = pre_input_tasks
    
    @classmethod
    def detect(cls, pre_input_tasks: Callable[[], None]) -> "DisplayServer":
        """Detects the current running Display server and returns and interface
        for interacting with it
        """
        xdg_session_type = os.getenv("XDG_SESSION_TYPE")
        # Check to see if DISPLAY is set anyways
        if xdg_session_type is None and os.getenv("DISPLAY") is not None:
            xdg_session_type = "x11"
        if xdg_session_type == "wayland":
            raise NotImplementedError(
                "Tests are not made to run under wayland "
                "because key presses are harder to send."
            )
        elif xdg_session_type == "x11":
            if not os.getenv("DISPLAY"):
                raise Exception("System reported x11 but didn't find $DISPLAY")
            return X11DisplayServer(pre_input_tasks)
        else:
            raise NotImplementedError(
                "Failed to detect which display server is being used."
            )

    @abc.abstractmethod
    def type_string(_cls, string: str):
        """Types string
        
        Calls pre_input_tasks before running"""
        raise NotImplementedError

    @abc.abstractmethod
    def press_keys(_cls, keys: KeyCode | list[KeyCode]):
        """Presses key"""
        raise NotImplementedError
    
    @abc.abstractmethod
    def is_window_open(_cls, window_name: str) -> bool:
        """Checks to see if there is a window open with the name"""
        raise NotImplementedError


class X11DisplayServer(DisplayServer):
    """Xorg (aka X11) display server"""

    _window_id: Optional[str]
    """Window to scope all keypresses to"""


    def __init__(
        self,
        pre_input_tasks: Callable[[], None]
    ):
        super().__init__(pre_input_tasks)

        # Check system binaries we need for this implementation
        for binary in ["xdotool"]:
            if not shutil.which(binary):
                raise MissingSystemBinary(binary)
            
        self._window_id = None
        
        # Try setting the window id
        try:
            self._window_id = self._search_for_window(self.window_name)
        except Exception:
            pass
    
    def _xdotool(
        self,
        args: list[str]
    ) -> subprocess.CompletedProcess[str]:
        """Runs xdotool
        
        Automatically handles the case where the window name changes
        """
        def _run() -> subprocess.CompletedProcess[str]:
            args_to_run = ["xdotool"]
            # If we haven't found our window id yet, try to set it
            if not self._window_id and self.window_name:
                self._window_id = self._search_for_window(self.window_name)
            
            if len(args) > 0:
                args_to_run += [args[0]]
                # Check to see if our subcommand is one with the --window parameter
                if self._window_id and args[0] in ["key", "type"]:
                    args_to_run += ["--window", self._window_id]
            
                args_to_run += args[1:]
            return run_cmd(args_to_run)
        # Run once, if fail with bad window try getting the window again and trying
        # one last time
        try:
            return _run()
        except CommandFailedError as e:
            # Check to see if we failed due to bad window - if so retry with new window
            if "X Error of failed request:  BadWindow (invalid Window parameter)" in e.stderr: #noqa: E501
                # Reset bad window
                self._window_id = None
                # try again (this function will set self._window_id)
                return _run()
            else:
                raise

    def type_string(self, string):
        """Uses xdotool to type a string"""
        self.pre_input_tasks()
        self._xdotool(["type", string])

    def press_keys(self, keys: KeyCode | list[KeyCode]):
        """Uses xdotool to press keys"""
        self.pre_input_tasks()
        if isinstance(keys, KeyCode):
            keys = [keys]
        x11_keys = [key.x11_code() for key in keys]
        for key in x11_keys:
            self._xdotool(["key", key])
            time.sleep(.5)

    def _search_for_window(self, window_name) -> str:
        return run_cmd(["xdotool", "search", "--name", window_name]).stdout.strip()

    def set_window(self, window_name: str):
        """Scope keypresses to window"""
        self._window_id = self._search_for_window(window_name)

    def is_window_open(self, window_name: str) -> bool:
        output = self._search_for_window(window_name)
        return len(output) > 0

def wait_for_directory_to_be_untouched(directory: str, period: float):
    def _check_for_directory_to_be_untouched():
        highest_modified_time: float = 0
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                file_mtime = (Path(dirpath) / filename).stat().st_mtime
                if file_mtime > highest_modified_time:
                    highest_modified_time = file_mtime
        current_time = time.time()

        if (current_time - highest_modified_time) > period:
            return True
        else:
            return False

    wait_for_true(_check_for_directory_to_be_untouched, timeout=None, period=period / 2)


def test_run(ou_dedetai: OuDedetai):
    ou_dedetai.stop_app()

    # First launch Run the app. This assumes that logos is spawned before this completes
    logos = ou_dedetai.start_app()

    # Preform the test - is the window open?
    wait_for_true(logos.is_window_open)

    # Cleanup after the test.
    ou_dedetai.stop_app()


def test_install() -> OuDedetai:
    ou_dedetai = OuDedetai(log_level="debug")
    ou_dedetai.uninstall()
    ou_dedetai.run(["--install-app", "--assume-yes"])
    return ou_dedetai


def test_first_run_resource_download(
    ou_dedetai: OuDedetai,
    logos_username: str,
    logos_password: str
):
    """Starts Logos and goes through the first run dialog with a given username/password

    Code was written for Logos v40, it may not function for newer/older versions if
    Logos changes the format of the first run dialog as it sends keyboard presses.

    Requires an isolated ou_dedetai
    """
    logos = ou_dedetai.start_app()

    # Wait for the Logos UI to display
    # time.sleep(10)
    # Now test to see if we can login.
    # This test is designed to take some time
    # Prefer more robust times over quicker tests.
    logos.type_string(logos_username)
    logos.press_keys(KeyCodeTab())
    logos.type_string(logos_password)
    logos.press_keys(KeyCodeReturn())
    # Time delay... This may be variable, but we have no way to check
    # Took 10 seconds on my machine, double for safety.
    time.sleep(20)

    # Three tabs and a space agrees with second option (essential/minimal). 
    # Some accounts with very little resources do not have 3 options, but 2.
    logos.press_keys([KeyCodeTab()] *4 + [KeyCodeSpace()])
    # Then shift+Tab three times to get to the continue button.
    # We need to use shift tab, as some accounts have three options in the radio
    # (Full/essential/minimal), others only have (full/minimal)
    # so we can't count on how many tabs to go down
    logos.press_keys(
        [KeyCodeModified(KeyCodeShift(), KeyCodeTab())] *3 
        + [KeyCodeReturn()]
    )
    # Wait for the UI to settle - we can wait here longer than we need to
    time.sleep(30)
    # Hit Continue again
    logos.press_keys([KeyCodeTab(), KeyCodeReturn()])
    # Now we wait for resources to download. Extremely variable.
    # The continue button isn't tab navigable at this point in the install
    #
    # Wait until no files have been touched for a minute
    # Then stop and restart logos. This should unstuck any stuck state.
    # For example when testing this my download got stuck at 66%
    # But stopping and restarting fixed.

    assert ou_dedetai.install_dir, "The test must start in isolated mode so we know where the install dir is realiably" #noqa: E501
    logos_appdata_dir = None
    for file in Path(ou_dedetai.install_dir).glob("data/wine64_bottle/drive_c/users/*/AppData/Local/Logos"): #noqa: E501
        logos_appdata_dir = str(file)
        break
    assert logos_appdata_dir

    wait_for_directory_to_be_untouched(logos_appdata_dir, 60)

    logos.close()

class WineDBGRunning(Exception):
    """Exception to keep track of when we noticed winedbg is running
    
    Useful as an exeception as it can be caught and ignored if desired."""


def is_winedbg_is_running() -> bool:
    if 'winedbg' in [proc.name() for proc in psutil.process_iter(['name'])]:
        return True
    return False

def raise_if_winedbg_is_running():
    """Raises exception if winedbg was found to be running"""
    if is_winedbg_is_running():
        raise WineDBGRunning

def test_logos_features(ou_dedetai: OuDedetai):
    """Tests various logos features to ensure it doesn't crash
    
    We can't confirm the features function in an automated fashion
    but we can check to see if they crash the application.
    """
    logos = ou_dedetai.start_app()
    # Now try to do some things

    # FIXME: after moving this to unittests, these should be different test cases

    # Open John 3.16 in the preferred bible
    logos.run_command_box("John 3:16")
    # Let it settle
    time.sleep(2)
    logos.run_command_box("Jesus factbook")

    logos.open_guide("bible word study")
    logos.type_string("worship")
    logos.press_keys(KeyCodeReturn())
    # Let it settle
    time.sleep(4)

    logos.open_tool("copy bible verses")

    # Now ensure the Logos window is still open
    if logos.is_crashed():
        raise TestFailed("Logos Crashed.")

    print("Logos opened all tools while staying open")
    logos.close()

def test_logos_crash_is_detected_by_test_code(ou_dedetai: OuDedetai):
    """It is very important to ensure that our test code is actually testing anything
    
    This scenario forces a known-crash - in this case a missing arial font and opening
    copy bible verses - to ensure our code detects that Logos did indeed crash."""
    # Now check to see if our test code properly detects a crash
    logos = ou_dedetai.start_app()

    assert ou_dedetai.install_dir, "This test only supports isolated installs"
    # Sabotage! For the sake of a crash. Still needs testing to force a crash. 
    # We may want to have a negative test for this to ensure our logic to detect
    # logos idn't crash still functions later on in time.
    # This may or may not work as the data might already be loaded.
    font_dir = f"{ou_dedetai.install_dir}/data/wine64_bottle/drive_c/windows/Fonts"
    fake_font_dir = font_dir + "_"
    shutil.move(font_dir, fake_font_dir)

    logos.open_tool("copy bible verses")
    # Let it settle
    time.sleep(2)

    # Cleanup after tests
    shutil.move(fake_font_dir, font_dir)

    # Ensure that Logos crashed
    if not logos.is_crashed():
        raise TestFailed("Logos should have crashed from a missing arial font.")
    
    # best-effort cleanup
    try:
        run_cmd(["pkill", "winedbg"])
    except Exception:
        pass

    print("Test code successfully detected Logos crash")

    logos.close()


def main():
    # FIXME: also test the beta channel of Logos?
    # FIXME: also test verbum
    # FIXME: add negative tests for when the installer fails (at different points)

    # FIXME: consider loop to run all of these in their supported distroboxes (https://distrobox.it/)
    # ou_dedetai = test_install()
    ou_dedetai = OuDedetai(log_level="debug", isolate=True)
    ou_dedetai.run(["--install-app", "--assume-yes"])

    # If we were given credentials, use them to login and download resources.
    # This may take some time.
    # Useful bash script to set these
    """
    export LOGOS_USERNAME=`read -p "Username: " foo;echo $foo`;
    export LOGOS_PASSWORD=`read -p "Password: " -s foo;echo $foo`;
    echo
    """
    logos_username = os.getenv("LOGOS_USERNAME")
    logos_password = os.getenv("LOGOS_PASSWORD")
    # These key sequences were tested on Logos 41.
    # If the installer changes form, we'll need to adjust this.
    if logos_username and logos_password:
        test_first_run_resource_download(ou_dedetai, logos_username, logos_password)
        
        # FIXME: also support loading from a backup to achieve the same state
        test_logos_features(ou_dedetai)


        test_logos_crash_is_detected_by_test_code(ou_dedetai)

    ou_dedetai.uninstall()


    # Untested:
    # - run_indexing - Need to be logged in
    # - edit-config - would need to modify EDITOR for this, not a lot of value
    # --install-dependencies - would be easy enough to run this, but not a real test
    #   considering the machine the tests are running on probably already has it
    #   installed and it's already run in install-all
    # --update-self - we might be able to fake it into thinking we're an older version
    # --update-latest-appimage - we're already at latest as a result of install-app
    # --install-* - already effectively tested as a result of install-app, may be 
    #   difficult to confirm independently
    # --set-appimage - just needs to be implemented
    # --get-winetricks - no need to test independently, covered in install_app
    # --run-winetricks - needs a way to cleanup after this spawns
    # --toggle-app-logging - difficult to confirm
    # --create-shortcuts - easy enough, unsure the use of this, shouldn't this already
    #   be done? Nothing in here should change? The user can always re-run the entire
    #   process if they want to do this
    # --winetricks - unsure how'd we confirm it work

    # Final message
    print("Tests passed.")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
