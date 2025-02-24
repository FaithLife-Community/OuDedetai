import atexit
from datetime import datetime
import enum
import inspect
import json
import logging
import os
import queue
import sqlite3
import inotify.adapters # type: ignore
import psutil
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
from ou_dedetai.app import App
from packaging.version import Version
from pathlib import Path
from typing import List, Optional, Tuple

from . import constants
from . import network
from . import system
from . import wine


# FIXME: This function isn't used and should probably be removed.
def get_calling_function_name():
    if 'inspect' in sys.modules:
        stack = inspect.stack()
        caller_frame = stack[1]
        caller_name = caller_frame.function
        return caller_name
    else:
        return "Inspect Not Enabled"


# FIXME: Not good practice to clobber a built-in [list] as a variable name.
def append_unique(list, item):
    if item not in list:
        list.append(item)
    else:
        logging.debug(f"{item} already in {list}.")


def die_if_running(app: App):

    def remove_pid_file():
        if os.path.exists(constants.PID_FILE):
            os.remove(constants.PID_FILE)

    if os.path.isfile(constants.PID_FILE):
        with open(constants.PID_FILE, 'r') as f:
            pid = f.read().strip()
            message = f"The script is already running on PID {pid}. Should it be killed to allow this instance to run?"  # noqa: E501
            if app.approve(message):
                os.kill(int(pid), signal.SIGKILL)

    atexit.register(remove_pid_file)
    with open(constants.PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def die(message):
    logging.critical(message)
    sys.exit(1)


def restart_lli():
    logging.debug(f"Restarting {constants.APP_NAME}.")
    pidfile = Path(constants.PID_FILE)
    if pidfile.is_file():
        pidfile.unlink()
    os.execv(sys.executable, [sys.executable])
    sys.exit()


def clean_all():
    logging.info("Cleaning all temp files…")
    os.system(f"rm -f {os.getcwd()}/wget-log*")
    logging.info("done")


def get_user_downloads_dir() -> str:
    home = Path.home()
    downloads_path = str(home / 'Downloads')

    xdg_config = Path(os.getenv('XDG_CONFIG_HOME', home / '.config'))
    user_dirs_file = xdg_config / 'user-dirs.dirs'
    if user_dirs_file.is_file():
        with user_dirs_file.open() as f:
            for line in f.readlines():
                if 'DOWNLOAD' in line:
                    downloads_path = line.rstrip().split('=')[1].replace(
                        '$HOME',
                        str(home)
                    ).strip('"')
                    break
    return downloads_path


def delete_symlink(symlink_path):
    symlink_path = Path(symlink_path)
    if symlink_path.is_symlink():
        try:
            symlink_path.unlink()
            logging.info(f"Symlink at {symlink_path} removed successfully.")
        except Exception as e:
            logging.error(f"Error removing symlink: {e}")


# FIXME: should this be in control?
def install_dependencies(app: App):
    if app.conf.faithlife_product_version:
        targetversion = int(app.conf.faithlife_product_version)
    else:
        targetversion = 10
    app.status(f"Checking {app.conf.faithlife_product} {str(targetversion)} dependencies…")

    if targetversion == 10:
        system.install_dependencies(app, target_version=10)  # noqa: E501
    elif targetversion == 9:
        app.status("Logos 9 not supported.", 100)
        app.exit("Logos 9 not supported.", False)
    else:
        logging.error(f"Unknown Target version, expecting 10 but got: {app.conf.faithlife_product_version}.") #noqa: E501

    app.status("Installed dependencies.", 100)


def file_exists(file_path: Optional[str | bytes | Path]) -> bool:
    if file_path is not None:
        expanded_path = os.path.expanduser(file_path)
        return os.path.isfile(expanded_path)
    else:
        return False


# FIXME: Surely the appropriate JSON filename and key name depend on Product
# Name and don't always include "Logos"?
def get_current_logos_version(logos_appdata_dir: Optional[str]) -> Optional[str]:
    if logos_appdata_dir is None:
        return None
    path = f"{logos_appdata_dir}/System/Logos.deps.json"  # noqa: E501
    logos_version_number: Optional[str] = None
    if Path(path).exists():
        with open(path, 'r') as json_file:
            json_data = json.load(json_file)
        for key in json_data.get('libraries', dict()):
            if key.startswith('Logos') and '/' in key:
                logos_version_number = key.split('/')[1]

        logging.debug(f"{logos_version_number=}")
        if logos_version_number is not None:
            return logos_version_number
        else:
            logging.debug("Couldn't determine installed Logos version.")
            return None
    return None


def check_logos_release_version(version, threshold, check_version_part):
    if version is not None:
        version_parts = list(map(int, version.split('.')))
        return version_parts[check_version_part - 1] < threshold
    else:
        return False


def filter_versions(versions, threshold, check_version_part):
    return [version for version in versions if check_logos_release_version(version, threshold, check_version_part)]  # noqa: E501


def get_winebin_code_and_desc(app: App, binary) -> Tuple[str, str | None]:
    """Gets the type of wine in use and it's description
    
    Returns:
        code: One of: Recommended, AppImage, System, Proton, PlayOnLinux, Custom
        description: Description of the above
    """
    # Set binary code, description, and path based on path
    codes = {
        "Recommended": "Use the recommended AppImage",
        "AppImage": "AppImage of Wine64",
        "System": "Use the system binary (i.e., /usr/bin/wine64). WINE must be 7.18-staging or later, or 8.16-devel or later, and cannot be version 8.0.",  # noqa: E501
        "Proton": "Install using the Steam Proton fork of WINE.",
        "PlayOnLinux": "Install using a PlayOnLinux WINE64 binary.",
        "Custom": "Use a WINE64 binary from another directory.",
    }
    # TODO: The GUI currently cannot distinguish between the recommended
    # AppImage and another on the system. We need to add some manner of making
    # this distinction in the GUI, which is why the wine binary codes exist.
    # Currently the GUI only accept an array with a single element, the binary
    # itself; this will need to be modified to a two variable array, at the
    # least, even if we hide the wine binary code, but it might be useful to
    # tell the GUI user that a particular AppImage/binary is recommended.
    # Below is my best guess for how to do this with the single element array…
    # Does it work?
    if isinstance(binary, Path):
        binary = str(binary)
    if binary == f"{app.conf.installer_binary_dir}/{app.conf.wine_appimage_recommended_file_name}":  # noqa: E501
        code = "Recommended"
    elif binary.lower().endswith('.appimage'):
        code = "AppImage"
    elif "/usr/bin/" in binary:
        code = "System"
    elif "Proton" in binary:
        code = "Proton"
    elif "PlayOnLinux" in binary:
        code = "PlayOnLinux"
    else:
        code = "Custom"
    desc = codes.get(code)
    logging.debug(f"{binary} code & desc: {code}; {desc}")
    return code, desc


def get_wine_options(app: App) -> List[str]:  # noqa: E501
    appimages = app.conf.wine_app_image_files
    binaries = app.conf.wine_binary_files
    logging.debug(f"{appimages=}")
    logging.debug(f"{binaries=}")
    wine_binary_options = []

    recomended_appimage = f"{app.conf.installer_binary_dir}/{app.conf.wine_appimage_recommended_file_name}" # noqa: E501

    if recomended_appimage in appimages:
        appimages.remove(recomended_appimage)

    # Add AppImages to list
    os_name, _ = system.get_os()
    if os_name != "alpine":
        wine_binary_options.append(recomended_appimage)
        wine_binary_options.extend(appimages)

    sorted_binaries = sorted(list(set(binaries)))
    logging.debug(f"{sorted_binaries=}")

    for wine_binary_path in sorted_binaries:
        # FIXME: The results of this function aren't used [anymore?].
        code, description = get_winebin_code_and_desc(app, wine_binary_path)  # noqa: E501

        # Create wine binary option array
        wine_binary_options.append(wine_binary_path)
    logging.debug(f"{wine_binary_options=}")
    return wine_binary_options


# FIXME: This function is not used and should probably be removed.
def get_procs_using_file(file_path):
    procs = set()
    for proc in psutil.process_iter(['pid', 'open_files', 'name']):
        try:
            paths = [f.path for f in proc.open_files()]
            if len(paths) > 0 and file_path in paths:
                procs.add(proc.pid)
        except psutil.AccessDenied:
            pass
    return procs


def find_installed_product(faithlife_product: str, wine_prefix: str) -> Optional[str]:
    if faithlife_product and wine_prefix:
        drive_c = Path(f"{wine_prefix}/drive_c/")
        name = faithlife_product
        exe = None
        for root, _, files in drive_c.walk(follow_symlinks=False):
            if root.name == name and f"{name}.exe" in files:
                exe = str(root / f"{name}.exe")
                break
        return exe
    return None


def enough_disk_space(dest_dir, bytes_required):
    free_bytes = shutil.disk_usage(dest_dir).free
    logging.debug(f"{free_bytes=}; {bytes_required=}")
    return free_bytes > bytes_required


def get_path_size(file_path):
    file_path = Path(file_path)
    if not file_path.exists():
        path_size = None
    else:
        path_size = sum(f.stat().st_size for f in file_path.rglob('*')) + file_path.stat().st_size  # noqa: E501
    return path_size


def get_folder_group_size(src_dirs: list[Path], q: queue.Queue[int]):
    src_size = 0
    for d in src_dirs:
        if not d.is_dir():
            continue
        src_size += get_path_size(d)
    q.put(src_size)


def get_latest_folder(folder_path):
    folders = [f for f in Path(folder_path).glob('*')]
    if not folders:
        logging.warning(f"No folders found in {folder_path}")
        return None
    folders.sort()
    logging.info(f"Found {len(folders)} backup folders.")
    latest = folders[-1]
    logging.info(f"Latest folder: {latest}")
    return latest


class VersionComparison(enum.Enum):
    OUT_OF_DATE = enum.auto()
    UP_TO_DATE = enum.auto()
    DEVELOPMENT = enum.auto()


def compare_logos_linux_installer_version(app: App) -> Optional[VersionComparison]:
    current = Version(constants.LLI_CURRENT_VERSION)
    latest = Version(app.conf.app_latest_version)

    if current < latest:
        # Current release is older than recommended.
        output = VersionComparison.OUT_OF_DATE
    elif current > latest:
        # Installed version is custom.
        output = VersionComparison.DEVELOPMENT
    elif current == latest:
        # Current release is latest.
        output = VersionComparison.UP_TO_DATE

    logging.debug(f"LLI self-update check: {output=}")
    return output


# FIXME: This actually compares any wine binary with recommended version. Maybe
# the function should be renamed to 'check_recommended_wine_version'?
def compare_recommended_appimage_version(app: App):
    status = None
    message = None
    wine_exe_path = app.conf.wine_binary
    wine_release, error_message = wine.get_wine_release(wine_exe_path)
    if wine_release is not None and wine_release is not False:
        current_version = Version(f"{wine_release.major}.{wine_release.minor}")
        logging.debug(f"Current wine release: {current_version}")

        recommended_version = Version(app.conf.wine_appimage_recommended_version)
        logging.debug(f"Recommended wine release: {recommended_version}")
        if current_version < recommended_version:
            # Current release is older than recommended.
            status = 0
            message = "yes"
        elif current_version == recommended_version:
            # Current release is latest.
            status = 1
            message = "uptodate"
        elif current_version > recommended_version:
            # Installed version is custom
            status = 2
            message = "no"
    else:
        # FIXME: should this raise an exception?
        status = -1
        message = f"Error: {error_message}"

    logging.debug(f"{status=}; {message=}")
    return status, message


def get_lli_release_version(lli_binary):
    lli_version = None
    # Ensure user-executable by adding 0o001.
    st = lli_binary.stat()
    os.chmod(lli_binary, mode=st.st_mode | stat.S_IXUSR)
    # Get version number.
    cmd = [lli_binary, '--version']
    vstr = subprocess.check_output(cmd, text=True)
    m = re.search(r'\d+\.\d+\.\d+(-[a-z]+\.\d+)?', vstr)
    if m:
        lli_version = m[0]
    return lli_version


def is_appimage(file_path):
    # Ref:
    # - https://cgit.freedesktop.org/xdg/shared-mime-info/commit/?id=c643cab25b8a4ea17e73eae5bc318c840f0e3d4b  # noqa: E501
    # - https://github.com/AppImage/AppImageSpec/blob/master/draft.md#image-format  # noqa: E501
    # Note:
    # result is a tuple: (is AppImage: True|False, AppImage type: 1|2|None)
    # result = (False, None)
    expanded_path = Path(file_path).expanduser().resolve()
    logging.debug(f"Converting path to expanded_path: {expanded_path}")
    if file_exists(expanded_path):
        logging.debug(f"{expanded_path} exists!")
        with expanded_path.open('rb') as f:
            f.seek(1)
            elf_sig = f.read(3)
            f.seek(8)
            ai_sig = f.read(2)
            f.seek(10)
            v_sig = f.read(1)

        appimage_check = elf_sig == b'ELF' and ai_sig == b'AI'
        appimage_type = int.from_bytes(v_sig)

        return appimage_check, appimage_type
    else:
        logging.error(f"File does not exist: {expanded_path}")
        return False, None


def check_appimage(filestr):
    logging.debug(f"Checking if {filestr} is a usable AppImage.")
    if filestr is None:
        logging.error("check_appimage: received None for file.")
        return False

    file_path = Path(filestr)

    appimage, appimage_type = is_appimage(file_path)
    if appimage:
        logging.debug("It is an AppImage!")
        if appimage_type == 1:
            logging.error(f"{file_path}: Can't handle AppImage version {str(appimage_type)} yet.")  # noqa: E501
            return False
        else:
            logging.debug("It is a usable AppImage!")
            return True
    else:
        logging.debug("It is not an AppImage!")
        return False


def find_appimage_files(app: App) -> list[str]:
    release_version = app.conf.installed_faithlife_product_release or app.conf.faithlife_product_version #noqa: E501
    appimages = []
    directories = [
        app.conf.installer_binary_dir,
        os.path.expanduser("~") + "/bin",
        app.conf.download_dir
    ]
    if app.conf._overrides.custom_binary_path is not None:
        directories.append(app.conf._overrides.custom_binary_path)

    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or higher is required for .rglob() flag `case-sensitive` ")  # noqa: E501

    for d in directories:
        appimage_paths = Path(d).glob('wine*.appimage', case_sensitive=False)
        for p in appimage_paths:
            if p is not None and check_appimage(p):
                output1, output2 = wine.check_wine_version_and_branch(
                    release_version,
                    p,
                    app.conf.faithlife_product_version
                )
                if output1 is not None and output1:
                    appimages.append(str(p))
                else:
                    logging.info(f"AppImage file {p} not added: {output2}")

    return appimages


def find_wine_binary_files(app: App, release_version: Optional[str]) -> list[str]:
    wine_binary_path_list = [
        "/usr/local/bin",
        os.path.expanduser("~") + "/bin",
        os.path.expanduser("~") + "/PlayOnLinux/wine/linux-amd64/*/bin",
        os.path.expanduser("~") + "/.steam/steam/steamapps/common/Proton*/files/bin",  # noqa: E501
    ]

    if app.conf._overrides.custom_binary_path is not None:
        wine_binary_path_list.append(app.conf._overrides.custom_binary_path)

    # Temporarily modify PATH for additional WINE64 binaries.
    for p in wine_binary_path_list:
        if p not in os.environ['PATH'] and os.path.isdir(p):
            os.environ['PATH'] = os.environ['PATH'] + os.pathsep + p

    # Check each directory in PATH for wine64; add to list
    binaries = []
    paths = os.environ["PATH"].split(":")
    for path in paths:
        binary_path = os.path.join(path, "wine64")
        if os.path.exists(binary_path) and os.access(binary_path, os.X_OK):
            binaries.append(binary_path)

    for binary in binaries[:]:
        output1, output2 = wine.check_wine_version_and_branch(
            release_version,
            binary,
            app.conf.faithlife_product_version
        )
        if output1 is not None and output1:
            continue
        else:
            binaries.remove(binary)
            logging.info(f"Removing binary: {binary} because: {output2}")

    return binaries


def set_appimage_symlink(app: App):
    # This function assumes make_skel() has been run once.
    if app.conf.wine_binary_code not in ["AppImage", "Recommended"]:
        logging.debug("AppImage commands disabled since we're not using an appimage")  # noqa: E501
        return
    if app.conf.wine_appimage_path is None:
        logging.debug("No need to set appimage symlink, as it wasn't set")
        return

    logging.debug(f"{app.conf.wine_appimage_path=}")
    logging.debug(f"{app.conf.wine_appimage_recommended_file_name=}")
    appimage_file_path = Path(app.conf.wine_appimage_path)
    appdir_bindir = Path(app.conf.installer_binary_dir)
    appimage_symlink_path = appdir_bindir / app.conf.wine_appimage_link_file_name

    destination_file_path = appdir_bindir / appimage_file_path.name  # noqa: E501

    if appimage_file_path.name == app.conf.wine_appimage_recommended_file_name:  # noqa: E501
        # Default case.
        # This saves in the install binary dir
        network.download_recommended_appimage(app)
    else:
        # Verify user-selected AppImage.
        if not check_appimage(appimage_file_path):
            app.exit(f"Cannot use {appimage_file_path}.")

        if destination_file_path != appimage_file_path:
            logging.info(f"Copying {destination_file_path} to {app.conf.installer_binary_dir}.")  # noqa: E501
            shutil.copy(appimage_file_path, destination_file_path)

    delete_symlink(appimage_symlink_path)
    os.symlink(destination_file_path, appimage_symlink_path)
    app.conf.wine_appimage_path = destination_file_path  # noqa: E501


def update_to_latest_lli_release(app: App):
    result = compare_logos_linux_installer_version(app)

    if constants.RUNMODE != 'binary':
        logging.error(f"Can't update {constants.APP_NAME} when run as {constants.RUNMODE}.")  # noqa: E501
    elif result == VersionComparison.OUT_OF_DATE:
        network.update_lli_binary(app=app)
    elif result == VersionComparison.UP_TO_DATE:
        logging.debug(f"{constants.APP_NAME} is already at the latest version.")
    elif result == VersionComparison.DEVELOPMENT:
        logging.debug(f"{constants.APP_NAME} is at a newer version than the latest.") # noqa: 501


# FIXME: consider moving this to control
def update_to_latest_recommended_appimage(app: App):
    if app.conf.wine_binary_code not in ["AppImage", "Recommended"]:
        logging.debug("AppImage commands disabled since we're not using an appimage")  # noqa: E501
        return
    app.conf.wine_appimage_path = Path(app.conf.wine_appimage_recommended_file_name)  # noqa: E501
    status, _ = compare_recommended_appimage_version(app)
    if status == 0:
        # TODO: Consider also removing old appimage from install dir. 
        set_appimage_symlink(app)
    elif status == 1:
        logging.debug("The AppImage is already set to the latest recommended.")
    elif status == 2:
        logging.debug("The AppImage version is newer than the latest recommended.")  # noqa: E501


def get_downloaded_file_path(download_dir: str, filename: str):
    dirs = [
        Path(download_dir),
        Path.home(),
        Path.cwd(),
    ]
    for d in dirs:
        file_path = Path(d) / filename
        if file_path.is_file():
            logging.info(f"'{filename}' exists in {str(d)}.")
            return str(file_path)
    logging.debug(f"File not found: {filename}")


def grep(regexp, filepath):
    fp = Path(filepath)
    found = None
    ct = 0
    if fp.exists():
        found = False
        with fp.open() as f:
            for line in f:
                ct += 1
                text = line.rstrip()
                if re.search(regexp, text):
                    logging.debug(f"{filepath}:{ct}:{text}")
                    found = True
    return found


def untar_file(file_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        with tarfile.open(file_path, 'r:gz') as tar:
            tar.extractall(path=output_dir)
            logging.debug(f"Successfully extracted '{file_path}' to '{output_dir}'")  # noqa: E501
    except tarfile.TarError as e:
        logging.error(f"Error extracting '{file_path}': {e}")


def is_relative_path(path: str | Path) -> bool:
    if isinstance(path, str):
        path = Path(path)
    return not path.is_absolute()


def get_relative_path(path: Path | str, base_path: str) -> str | Path:
    if is_relative_path(path):
        return path
    else:
        if isinstance(path, Path):
            path = str(path)
        base_path = str(base_path)
        if path.startswith(base_path):
            return path[len(base_path):].lstrip(os.sep)
        else:
            return path


def stopwatch(start_time=None, interval=10.0):
    if start_time is None:
        start_time = time.time()

    current_time = time.time()
    elapsed_time = current_time - start_time

    if elapsed_time >= interval:
        last_log_time = current_time
        return True, last_log_time
    else:
        return False, start_time


def get_timestamp():
    return datetime.today().strftime('%Y-%m-%dT%H%M%S')


def parse_bool(string: str) -> bool:
    return string.lower() in ['true', '1', 'y', 'yes']


def watch_db(path: str, sql_statements: list[str]):
    """Runs SQL statements against a sqlite db once to start with, then again every time
    The sqlite db is written to.
    
    Handles -wal/-shm as well

    This function may run infinitely, spawn it on it's own thread
    """
    # Silence inotify logs
    logging.getLogger('inotify').setLevel(logging.CRITICAL)
    i = inotify.adapters.Inotify()
    i.add_watch(path)

    def execute_sql(cur):
        # logging.debug(f"Executing SQL against {path}: {sql_statements}")
        for statement in sql_statements:
            try:
                cur.execute(statement)
            # Database may be locked, keep trying later.
            except sqlite3.OperationalError:
                logging.exception("Best-effort db update failed")
                pass

    with sqlite3.connect(path, autocommit=True) as con:
        cur = con.cursor()

        # Execute once before we start the loop
        execute_sql(cur)
        swallow_one = True

        # Keep track of if we've added -wal and -shm are added yet
        # They may not exist when we start
        watching_wal_and_shm = False
        for event in i.event_gen(yield_nones=False):
            (_, type_names, _, _) = event
            # These files may not exist when it's executes for the first time
            if (
                not watching_wal_and_shm
                and Path(path + "-wal").exists()
                and Path(path + "-shm").exists()
            ):
                i.add_watch(path + "-wal")
                i.add_watch(path + "-shm")
                watching_wal_and_shm = True

            if 'IN_MODIFY' in type_names or 'IN_CLOSE_WRITE' in type_names:
                # Check to make sure that we aren't responding to our own write
                if swallow_one:
                    swallow_one = False
                    continue
                execute_sql(cur)
                swallow_one = True
        # Shouldn't be possible to get here, but on the off-chance it happens, 
        # we'd like to know and cleanup
        logging.debug(f"Stopped watching {path}")
