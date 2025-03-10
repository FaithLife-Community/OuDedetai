import os
from pathlib import Path
import signal
import subprocess
import time
from enum import Enum
import logging
import psutil
import threading

from ou_dedetai import database
from ou_dedetai.app import App

from . import system
from . import utils
from . import wine


class State(Enum):
    RUNNING = 1
    STOPPED = 2
    STARTING = 3
    STOPPING = 4


class LogosManager:
    def __init__(self, app: App):
        self.logos_state = State.STOPPED
        self.indexing_state = State.STOPPED
        self.app = app
        self.processes: dict[str, subprocess.Popen] = {}
        """These are sub-processes we started"""
        self.existing_processes: dict[str, list[psutil.Process]] = {}
        """These are processes we discovered already running"""

    def monitor_indexing(self):
        if self.app.conf.logos_indexer_exe in self.existing_processes:
            indexer = self.existing_processes.get(self.app.conf.logos_indexer_exe)
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
        if self.app.conf.logos_login_exe:
            login = self.existing_processes.get(self.app.conf.logos_login_exe, [])
        if self.app.conf.logos_cef_exe:
            cef = self.existing_processes.get(self.app.conf.logos_cef_exe, [])

        splash_running = splash[0].is_running() if splash else False
        login_running = login[0].is_running() if login else False
        cef_running = cef[0].is_running() if cef else False
        # logging.debug(f"{self.logos_state=}")
        # logging.debug(f"{splash_running=}; {login_running=}; {cef_running=}")

        if self.logos_state == State.STARTING:
            if login_running or cef_running:
                self.logos_state = State.RUNNING
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
        if app.conf.logos_exe:
            self.existing_processes[app.conf.logos_exe] = system.get_pids(app.conf.logos_exe)
        if app.conf.wine_user:
            # Also look for the system's Logos.exe (this may be the login window)
            logos_system_exe = (
                f"C:\\users\\{app.conf.wine_user}\\AppData\\Local\\{app.conf.faithlife_product}\\System\\"
                f"{app.conf.faithlife_product}.exe"
            )
            self.existing_processes[logos_system_exe] = system.get_pids(logos_system_exe)
        if app.conf.logos_indexer_exe:
            self.existing_processes[app.conf.logos_indexer_exe] = system.get_pids(app.conf.logos_indexer_exe)
        if app.conf.logos_cef_exe:
            self.existing_processes[app.conf.logos_cef_exe] = system.get_pids(app.conf.logos_cef_exe)

    def monitor(self):
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

    def start(self):
        self.logos_state = State.STARTING
        wine_release, _ = wine.get_wine_release(self.app.conf.wine_binary)

        def run_logos():
            self.prevent_logos_updates()
            self.set_auto_updates(False)
            if not self.app.conf.logos_exe:
                raise ValueError("Could not find installed Logos EXE to run")
            process = wine.run_wine_proc(
                self.app.conf.wine_binary,
                self.app,
                exe=self.app.conf.logos_exe
            )
            if process is not None:
                self.processes[self.app.conf.logos_exe] = process
            self.logos_state = State.RUNNING

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
            if not self.app.conf.logos_indexer_exe:
                raise ValueError("Cannot find installed indexer")
            process = wine.run_wine_proc(
                self.app.conf.wine_binary,
                app=self.app,
                exe=self.app.conf.logos_indexer_exe
            )
            if process is not None:
                self.processes[self.app.conf.logos_indexer_exe] = process

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
            for process_name in [self.app.conf.logos_indexer_exe]:
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
                'HKCU\\Software\\Logos4\\Logging',
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
        exe_args = [
            'add', 'HKCU\\Software\\Logos4\\Logging', '/v', 'Enabled',
            '/t', 'REG_DWORD', '/d', value, '/f'
        ]
        process = wine.run_wine_proc(
            self.app.conf.wine_binary,
            app=self.app,
            exe='reg',
            exe_args=exe_args
        )
        if process:
            process.wait()
        wine.wineserver_wait(self.app)
        self.app.conf.faithlife_product_logging = state == state_enabled
