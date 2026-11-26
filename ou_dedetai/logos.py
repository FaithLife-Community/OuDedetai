import os
from pathlib import Path
import signal
import subprocess
import time
from enum import Enum
import logging
import psutil
import threading
from typing import Optional

from ou_dedetai import constants, database
from ou_dedetai.app import App
from ou_dedetai.config import get_logos_user_id

from . import system
from . import utils
from . import wine


# How long start() waits for Logos's processes before giving up (a slow first start included)
STARTING_TIMEOUT = 300


class State(Enum):
    RUNNING = 1
    STOPPED = 2
    STARTING = 3
    STOPPING = 4


class LogosManager:
    def __init__(self, app: App):
        self.logos_state = State.STOPPED
        self.starting_since = 0.0
        """When start() last ran: how long Logos's processes have had to appear."""
        self.indexing_state = State.STOPPED
        self.app = app
        self.processes: dict[str, subprocess.Popen] = {}
        """These are sub-processes we started"""
        self.existing_processes: dict[str, list[psutil.Process]] = {}
        """These are processes we discovered already running"""

    def monitor_indexing(self):
        if self.app.conf.logos_indexer_exe_windows_path in self.existing_processes:
            indexer = self.existing_processes.get(self.app.conf.logos_indexer_exe_windows_path)
            if indexer and isinstance(indexer[0], psutil.Process) and indexer[0].is_running():
                self.indexing_state = State.RUNNING
            else:
                self.indexing_state = State.STOPPED

    def monitor_logos(self):
        splash = []
        login = []
        cef = []
        if self.app.conf.logos_exe:
            splash = self.existing_processes.get(self.app.conf.logos_exe, [])
        if self.app.conf.logos_system_exe_windows_path:
            login = self.existing_processes.get(self.app.conf.logos_system_exe_windows_path, [])
        if self.app.conf.logos_cef_exe_windows_path:
            cef = self.existing_processes.get(self.app.conf.logos_cef_exe_windows_path, [])

        splash_running = splash[0].is_running() if splash else False
        login_running = login[0].is_running() if login else False
        cef_running = cef[0].is_running() if cef else False
        # logging.debug(f"{self.logos_state=}")
        # logging.debug(f"{splash_running=}; {login_running=}; {cef_running=}")

        if self.logos_state == State.STARTING:
            if login_running or cef_running:
                self.logos_state = State.RUNNING
            elif (not splash_running and self.starting_since
                    and time.monotonic() - self.starting_since > STARTING_TIMEOUT):
                logging.warning(f"Logos didn't start within {STARTING_TIMEOUT} seconds.")
                self.logos_state = State.STOPPED
        elif self.logos_state == State.RUNNING:
            if not any((splash_running, login_running, cef_running)):
                self.stop()
        elif self.logos_state == State.STOPPING:
            pass
        elif self.logos_state == State.STOPPED:
            if splash_running:
                self.logos_state = State.STARTING
            if login_running:
                self.logos_state = State.RUNNING
            if cef_running:
                self.logos_state = State.RUNNING

    def get_logos_pids(self):
        app = self.app
        # FIXME: consider refactoring to make one call to get a system pids
        # Currently this gets all system pids 4 times
        for exe_path in [
            app.conf.logos_exe,
            app.conf.logos_system_exe_windows_path,
            app.conf.logos_indexer_exe_windows_path,
            app.conf.logos_cef_exe_windows_path
        ]:
            if exe_path:
                self.existing_processes[exe_path] = system.get_pids(exe_path)

    def hand_off_link(self) -> bool:
        """If Logos is already running, pass the pending link straight to it.

        Returns True when it did, so nothing else (tray, monitoring, a second start)
        happens: that is the sign-in callback's path and must stay a plain hand-off."""
        link = self.app.conf._overrides.logos_link
        if not link:
            return False
        self.monitor()
        if self.logos_state not in (State.STARTING, State.RUNNING):
            return False
        self.send_link(link)
        self.app.conf._overrides.logos_link = None
        return True

    def send_link(self, url: str) -> None:
        """Pass a link to the running Logos, as Logos.exe <link> does on Windows."""
        logging.info(f"Handing Logos a {url.split(':', 1)[0]}: link.")
        if not self._run_quietly(self.app.conf.logos_exe, [url], timeout=60):
            logging.warning("Timeout: Logos took over a minute to take the link.")

    def _run_quietly(self, exe: Optional[str], args: list[str], timeout: float, kill_late: bool = False) -> bool:
        """Run a Windows program in the prefix, output discarded; False if it took longer
        than `timeout` seconds (it's then stopped with kill_late, otherwise left running)."""
        with open(os.devnull, "w") as devnull:
            process = wine.run_wine_process(self.app, self.app.conf.wine_binary, devnull, devnull,
                                            exe=exe, exe_args=args)
        if process is None:
            return True
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if kill_late:
                process.kill()
            return False
        return True

    def reap_finished(self):
        """Collect the exit of Wine processes we started that have ended on their own
        (e.g. the user closed Logos). Otherwise they stay as <defunct> entries while
        Ou Dedetai runs, and tools looking for Logos.exe think it's still running."""
        for name, process in list(self.processes.items()):
            if process.poll() is not None:
                del self.processes[name]

    def monitor(self):
        self.reap_finished()
        if self.app.is_installed():
            self.get_logos_pids()
            try:
                self.monitor_indexing()
                self.monitor_logos()
            except Exception as e:
                # pass
                logging.error(e)
        else:
            # Useful if the install directory got deleted while executing
            self.logos_state = State.STOPPED

    def monitor_for_potential_issues(self):
        """A function to be run in parallel with running Logos to detect common issues and suggest workarounds"""
        # Make sure we have a logos appdata, without it we can't reliably do any checks
        logos_appdata_dir = self.app.conf._logos_appdata_dir
        if logos_appdata_dir is None:
            logging.warning("The user should have installed the Logos application by now and have this populated."
                            " Waiting until that is resolved…")
            while logos_appdata_dir is None:
                time.sleep(1)
                logos_appdata_dir = self.app.conf._logos_appdata_dir
        
        # See if the user is logged in, this may change which things we look for
        is_user_logged_in: bool = False
        if get_logos_user_id(logos_appdata_dir) is not None:
            is_user_logged_in = True

        sent_trouble_signing_in_message: bool = False

        time_logos_started = time.time()

        # Stop with Logos (or with Ou Dedetai: the thread is a daemon).
        while self.logos_state in (State.STARTING, State.RUNNING):
            # Now we wait...
            time.sleep(10)

            if not is_user_logged_in:
                if get_logos_user_id(logos_appdata_dir) is not None:
                    # User's now logged in - no fuss.
                    is_user_logged_in = True
                else:
                    # Took me about ~1.5 minutes to sign on while simulating a little dilly-dallying and a couple
                    # incorrect password attempts. Should still be longer than most people take to sign on, but not SO
                    # long that people close OD in frustration to try again - fine line of balance.
                    if not sent_trouble_signing_in_message and time.time() - time_logos_started > 60 * 1.75:
                        # It's been five minutes since the user launched Logos and yet they haven't logged in yet.
                        # Are they having trouble?
                        self.app.pop_up(
                            "Trouble Signing In?",
                            "If you're having trouble signing in, try these workarounds:\n\n" \
                            "If the browser isn't launching after you hit \"Sign In\" in the Logos application "
                            "consider installing firefox from your system's package manager and temporarily setting "
                            "that as your default browser.\n\n"
                            "If the browser opens and entering your credentials is successful but nothing happens: "
                            "on the Logos browser page try hitting the button for not being redirected automatically "
                            "then click on the link that shows up that suggests to click it if you're still having "
                            "trouble. That should cause you to sign in on the Logos application.\n\n"
                            f"If you still need help use \"Get Support\" on the main page of {constants.APP_NAME}"
                        )
                        # We only want to send this message once
                        sent_trouble_signing_in_message = True


    def start(self):
        self.logos_state = State.STARTING
        self.starting_since = time.monotonic()
        wine_release, _ = wine.get_wine_release(self.app.conf.wine_binary)

        def run_logos():
            if wine.wine_supports_logos_updates(wine_release):
                # This Wine can apply Logos's own updates without losing data.
                logging.info("Wine build supports Logos updates; leaving application updates in place.")
                wine.allow_logos_updates(self.app, self.app.conf.wine_binary)
            else:
                self.prevent_logos_updates()
            self.set_auto_updates(False)
            if not self.app.conf.logos_exe:
                raise ValueError("Could not find installed Logos EXE to run")
            # A link from the link handler (sign-in, Bible links) goes on Logos's command
            # line, as Logos.exe <link> does on Windows. Used once.
            link = self.app.conf._overrides.logos_link
            self.app.conf._overrides.logos_link = None
            process = wine.run_wine_application(
                self.app,
                self.app.conf.wine_binary,
                exe=self.app.conf.logos_exe,
                exe_args=[link] if link else None,
            )
            if process is not None:
                self.processes[self.app.conf.logos_exe] = process
            # Stay STARTING: monitor() moves to RUNNING once Logos's processes appear.
            # Marked RUNNING here, a monitor() call made before Wine has started
            # Logos.exe would see "running, but no processes" and stop it again.

        # Ensure wine version is compatible with Logos release version.
        good_wine, reason = wine.check_wine_rules(
            wine_release,
            self.app.conf.installed_faithlife_product_release,
            self.app.conf.faithlife_product_version
        )
        if not good_wine:
            self.app.exit(reason)
        else:
            if reason is not None:
                logging.debug(f"Warning: Wine Check: {reason}")
            wine.wineserver_kill(self.app)
            # Don't send "Running" message to GUI b/c it never clears.
            logging.info(f"Running {self.app.conf.faithlife_product}…")
            # A daemon: when the window quits while Logos runs ("Quit anyway"), nothing updates
            # logos_state any more, and a non-daemon thread would keep the process alive for good.
            self.app.start_thread(self.monitor_for_potential_issues)
            self.app.start_thread(run_logos, daemon_bool=False)
            # NOTE: The following code would keep the CLI open while running
            # Logos, but since wine logging is sent directly to wine.log,
            # there's no terminal output to see. A user can see that output by:
            # tail -f ~/.local/state/FaithLife-Community/wine.log
            # from ou_dedetai.cli import CLI
            # if isinstance(self.app, CLI):
            #     run_logos()
            #     self.monitor()
            #     while self.processes.get(app.conf.logos_exe) is None:
            #         time.sleep(0.1)
            #     while self.logos_state != State.STOPPED:
            #         time.sleep(0.1)
            #         self.monitor()

    # For now enforce this all the time, ideally we wouldn't override the user's choice
    # But risks as they are, setting it to false is safer for now.
    # Feel free to revisit when there is less chances of it breaking an install
    def set_auto_updates(self, val: bool):
        """Edits Logos' internal db entry corresponding to the option in:
        Program Settings -> Internet -> Automatically Download New Resources
        """
        if self.app.conf._logos_appdata_dir is None:
            return
        logos_appdata_dir = Path(self.app.conf._logos_appdata_dir)
        logos_user_id = self.app.conf._logos_user_id
        if not logos_user_id:
            return None
        db_path = logos_appdata_dir / "Documents" / logos_user_id / "LocalUserPreferences" / "PreferencesManager.db" 
        sql = (
            """UPDATE Preferences SET Data='<data """ +
            ('OptIn="true"' if val else 'OptIn="false"') +
            """ StartDownloadHour="0" StopDownloadHour="0" MarkNewResourcesAsCloud="true" />' """
            """ WHERE Type='UpdateManagerPreferences'""" 
        )
        self.app.start_thread(database.watch_db, str(db_path), [sql])

    def prevent_logos_updates(self):
        """Edits Logos' internal database to remove pending installers
        before it has a chance to apply them
        """
        if self.app.conf._logos_appdata_dir is None:
            return
        logos_appdata_dir = Path(self.app.conf._logos_appdata_dir)
        logos_user_id = self.app.conf._logos_user_id
        if logos_user_id is None:
            return None
        db_path = logos_appdata_dir / "Data" / logos_user_id / "UpdateManager" / "Updates.db"
        # FIXME: I wonder if we can use the result of these deletion using RETURNING
        # Then we could notify the user that there are updates.
        # If we do that we'd have to consider if their other resources are up to date
        # AND if their library is index and their library is prepared.
        # Logos probably should be off for this
        sql = [
            # "DELETE FROM Installers WHERE 1",
            # Cleanup the Update Ids that are associated with an application update
            "DELETE FROM UpdateUrls WHERE UpdateId IN " +
                "(SELECT UpdateId FROM Updates WHERE Source='Application Update')",
            # Cleanup database relations and removes Application Updates
            # Fixes corrupt DBs caused by an earlier
            # version of the software #275
            # If we don't do this, the application will crash when it tries to update.
            "DELETE FROM Updates WHERE UpdateId NOT IN "+
                "(SELECT UpdateId FROM UpdateUrls) OR "+
                "Source='Application Update'",
            # Also remove any UpdateId references that don't exist
            "UPDATE Resources SET Status=1, UpdateId=NULL WHERE UpdateId IS NOT NULL "+
                "AND UpdateId NOT IN (SELECT UpdateId FROM Updates)"
        ]
        self.app.start_thread(database.watch_db, str(db_path), sql)

    # Also noticed if the database Data/*/CloudResourceManager/CloudResources.db 
    # table TransitionStates has a ResourceId that isn't registered in UpdateManager,
    # logos will crash on startup. It can be recovered by removing those TransitionState
    # entries.
    # Perhaps we should attempt to recover in this state.
    # Since there are no known user interaction steps to get into this state, leaving it
    # alone for now. Only found it when manually modifying the database.

    def stop(self):
        logging.debug("Stopping LogosManager.")
        self.logos_state = State.STOPPING
        if len(self.existing_processes) == 0:
            self.get_logos_pids()

        pids: list[str] = []
        for processes in self.processes.values():
            pids.append(str(processes.pid))

        for existing_processes in self.existing_processes.values():
            pids.extend(str(proc.pid) for proc in existing_processes)

        if pids:
            try:
                system.run_command(['kill', '-9'] + pids)
                logging.debug(f"Stopped Logos processes at PIDs {', '.join(pids)}.")
            except Exception as e:
                logging.debug(f"Error while stopping Logos processes: {e}.")
        else:
            logging.debug("No Logos processes to stop.")
        self.logos_state = State.STOPPED
        # The Logos process has exited, if we wait here it hangs
        # wine.wineserver_wait(self.app)

    # How long a polite close may take before the user is offered a forced one.
    CLOSE_PATIENCE = 60
    # Logos counts as busy (probably syncing or saving) above this CPU use or disk writing.
    BUSY_CPU_PERCENT = 5.0
    BUSY_WRITE_BYTES = 256 * 1024

    def request_close(self) -> None:
        """Ask Logos to close, as clicking its window's close button does (Wine's taskkill
        without /F sends WM_CLOSE), so it can finish syncing and ask about unsaved work."""
        exe = Path(self.app.conf.logos_exe).name if self.app.conf.logos_exe else "Logos.exe"
        logging.info(f"Asking {exe} to close.")
        if not self._run_quietly("taskkill", ["/IM", exe], timeout=30, kill_late=True):
            logging.warning("taskkill took over 30 seconds.")

    def _logos_processes(self) -> list:
        return [p for procs in self.existing_processes.values() for p in procs
                if isinstance(p, psutil.Process)]

    def busy(self, interval: float = 1.0) -> bool:
        """Whether Logos appears to be working, e.g. syncing with Faithlife or saving:
        noticeable CPU use or disk writing over `interval` seconds. A Logos that is only
        waiting (say on an "unsaved changes?" question) is idle. A guess, not a promise."""
        processes = self._logos_processes()
        before: dict[int, int] = {}
        for p in processes:
            try:
                p.cpu_percent(None)
                before[p.pid] = p.io_counters().write_bytes
            except (psutil.Error, AttributeError):
                pass
        time.sleep(interval)
        cpu = 0.0
        written = 0
        for p in processes:
            try:
                cpu += p.cpu_percent(None)
                written += p.io_counters().write_bytes - before.get(p.pid, 0)
            except (psutil.Error, AttributeError):
                pass
        return cpu > self.BUSY_CPU_PERCENT or written > self.BUSY_WRITE_BYTES

    def close(self, timeout: float = CLOSE_PATIENCE, progress=None) -> bool:
        """Ask Logos to close and wait while it does. Returns True once it has closed, or
        False after `timeout` idle seconds (it may be asking a question): nothing is ever
        forced here. While Logos is busy (probably syncing) the wait goes on.
        `progress(busy, idle_seconds)` is called about once a second; returning True
        stops the wait (False is returned)."""
        if self._closed():
            return True
        self.request_close()
        idle_since = time.monotonic()
        while True:
            busy = self.busy()
            if self._closed():
                return True
            if busy:
                idle_since = time.monotonic()
            idle = time.monotonic() - idle_since
            if progress and progress(busy, idle):
                return False
            if idle > timeout:
                logging.info("Logos is still open after being asked to close.")
                return False

    def close_or_force(self) -> None:
        """Stop for the CLI and TUI: close politely, and force it only if the user agrees."""
        def progress(busy: bool, _idle: float) -> None:
            self.app.status("Logos appears to be syncing or saving; waiting for it to finish…" if busy
                            else "Waiting for Logos to close…")
        if self.close(progress=progress):
            self.app.status("Logos has closed.", 100)
            return
        if self.app.conf._overrides.assume_yes:
            self.app.status("Logos is still open; not forcing it to close unattended.")
            return
        if self.app.approve(
            "Force Logos to close?",
            "Logos hasn't closed. It may be asking you something (check its window). Forcing it to "
            "close can lose changes that haven't synced to your Faithlife account yet.",
        ):
            self.force_close()

    def force_close(self) -> None:
        """Force Logos to close, then end whatever else is still running in its Wine prefix
        (wineserver, services, leftover CEF processes), so nothing is left behind (#412).
        Only after the user has agreed: unsynced changes may be lost."""
        self.stop()
        wine.wineserver_kill(self.app)

    def _closed(self) -> bool:
        self.monitor()
        return self.logos_state == State.STOPPED

    def end_processes(self):
        for process_name, process in self.processes.items():
            if isinstance(process, subprocess.Popen):
                logging.debug(f"Found {process_name} in Processes. Attempting to close {process}.")
                try:
                    process.terminate()
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    os.waitpid(-process.pid, 0)

    def index(self):
        self.indexing_state = State.STARTING
        index_finished = threading.Event()

        def run_indexing():
            if not self.app.conf.logos_indexer_exe_windows_path:
                raise ValueError("Cannot find installed indexer")
            process = wine.run_wine_application(
                app=self.app,
                wine_binary=self.app.conf.wine_binary,
                exe=self.app.conf.logos_indexer_exe_windows_path
            )
            if process is not None:
                self.processes[self.app.conf.logos_indexer_exe_windows_path] = process

        def check_if_indexing(process: threading.Thread):
            start_time = time.time()
            last_time = start_time
            update_send = 0
            while process.is_alive():
                update, last_time = utils.stopwatch(last_time, 3)
                if update:
                    update_send = update_send + 1
                if update_send == 10:
                    total_elapsed_time = time.time() - start_time
                    elapsed_min = int(total_elapsed_time // 60)
                    elapsed_sec = int(total_elapsed_time % 60)
                    formatted_time = f"{elapsed_min}m {elapsed_sec}s"
                    self.app.status(f"Indexing is running… (Elapsed Time: {formatted_time})")
                    update_send = 0
            index_finished.set()

        def wait_on_indexing():
            index_finished.wait()
            self.indexing_state = State.STOPPED
            self.app.status("Indexing has finished.", percent=100)
            wine.wineserver_wait(app=self.app)

        wine.wineserver_kill(self.app)
        self.app.status("Indexing has begun…", 0)
        index_thread = self.app.start_thread(run_indexing, daemon_bool=False)
        self.indexing_state = State.RUNNING
        self.app.start_thread(
            check_if_indexing,
            index_thread,
            daemon_bool=False
        )
        self.app.start_thread(wait_on_indexing, daemon_bool=False)

    def stop_indexing(self):
        self.indexing_state = State.STOPPING
        if self.app:
            pids = []
            for process_name in [self.app.conf.logos_indexer_exe_windows_path]:
                if process_name is None:
                    continue
                process = self.processes.get(process_name)
                if process:
                    pids.append(str(process.pid))
                else:
                    logging.debug(f"No LogosIndexer processes found for {process_name}.")

            if pids:
                try:
                    system.run_command(['kill', '-9'] + pids)
                    self.indexing_state = State.STOPPED
                    self.app.status(f"Stopped LogosIndexer processes at PIDs {', '.join(pids)}.")
                except Exception as e:
                    logging.debug(f"Error while stopping LogosIndexer processes: {e}.")
            else:
                logging.debug("No LogosIndexer processes to stop.")
                self.indexing_state = State.STOPPED
        wine.wineserver_wait(app=self.app)

    def get_app_logging_state(self, init=False):
        state = 'DISABLED'
        try:
            current_value = wine.get_registry_value(
                f"HKCU\\{constants.REG_LOGOS_LOGGING}",
                'Enabled',
                self.app
            )
        except Exception as e:
            logging.warning(f"Failed to determine if logging was enabled, assuming no: {e}") 
            current_value = None
        if current_value == '0x1':
            state = 'ENABLED'
        return state

    def switch_logging(self, action=None):
        state_disabled = 'DISABLED'
        value_disabled = '0000'
        state_enabled = 'ENABLED'
        value_enabled = '0001'
        if action == 'disable':
            value = value_disabled
            state = state_disabled
        elif action == 'enable':
            value = value_enabled
            state = state_enabled
        else:
            current_state = self.get_app_logging_state()
            logging.debug(f"app logging {current_state=}")
            if current_state == state_enabled:
                value = value_disabled
                state = state_disabled
            else:
                value = value_enabled
                state = state_enabled

        logging.info(f"Setting app logging to '{state}'.")
        wine.reg_add(self.app, self.app.conf.wine_binary, f"HKCU\\{constants.REG_LOGOS_LOGGING}", 'Enabled',
                     'REG_DWORD', value)
        wine.wineserver_wait(self.app)
        self.app.conf.faithlife_product_logging = state == state_enabled
