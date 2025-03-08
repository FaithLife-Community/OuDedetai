"""These functions take no arguments by default.
They can be called from CLI, GUI, or TUI.
"""

import copy
import glob
import json
import logging
import queue
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
import webbrowser
from zipfile import ZipFile

from ou_dedetai import constants
from ou_dedetai.app import App

from . import system
from . import utils


def edit_file(config_file: str):
    system.run_command(["xdg-open", config_file])


def backup(app: App):
    backup_and_restore(mode="backup", app=app)


def restore(app: App):
    backup_and_restore(mode="restore", app=app)


# FIXME: almost seems like this is long enough to reuse the install_step count in app
# for a more detailed progress bar
# FIXME: consider moving this into it's own file/module.
def backup_and_restore(mode: str, app: App):
    app.status(f"Starting {mode}…")
    data_dirs = ["Data", "Documents", "Users"]
    backup_dir = Path(app.conf.backup_dir).expanduser().resolve()

    verb = "Use" if mode == "backup" else "Restore backup from"
    if not app.approve(f'{verb} existing backups folder "{app.conf.backup_dir}"?'):  # noqa: E501
        # Reset backup dir.
        # The app will re-prompt next time the backup_dir is accessed
        app.conf._raw.backup_dir = None

    # Set source folders.
    backup_dir = Path(app.conf.backup_dir)
    try:
        backup_dir.mkdir(exist_ok=True, parents=True)
    except PermissionError:
        verb = "access"
        if mode == "backup":
            verb = "create"
        app.exit(f"Can't {verb} folder: {backup_dir}")

    if mode == "restore":
        restore_dir = utils.get_latest_folder(app.conf.backup_dir)
        restore_dir = Path(restore_dir).expanduser().resolve()
        # FIXME: Shouldn't this prompt this prompt the list of backups?
        # Rather than forcing the latest
        # Offer to restore the most recent backup.
        if not app.approve(f"Restore most-recent backup?: {restore_dir}", ""):  # noqa: E501
            # Reset and re-prompt
            app.conf._raw.backup_dir = None
            restore_dir = utils.get_latest_folder(app.conf.backup_dir)
            restore_dir = Path(restore_dir).expanduser().resolve()
        source_dir_base = restore_dir
    else:
        if not app.conf._logos_appdata_dir:
            app.exit("Cannot backup, Logos installation not found")
        source_dir_base = app.conf._logos_appdata_dir
    src_dirs = [
        source_dir_base / d for d in data_dirs if Path(source_dir_base / d).is_dir()
    ]  # noqa: E501
    logging.debug(f"{src_dirs=}")
    if not src_dirs:
        app.exit(f"No files to {mode}")

    if mode == "backup":
        app.status("Backing up data…")
    else:
        app.status("Restoring data…")

    # Get source transfer size.
    q: queue.Queue[int] = queue.Queue()
    message = "Calculating backup size…"
    app.status(message)
    i = 0
    t = app.start_thread(utils.get_folder_group_size, src_dirs, q)
    try:
        while t.is_alive():
            i += 1
            i = i % 20
            app.status(f"{message}{'.' * i}\r")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        app.exit("Cancelled with Ctrl+C.")
    t.join()
    src_size = q.get()
    if src_size == 0:
        app.exit(f"Nothing to {mode}!")

    # Set destination folder.
    if mode == "restore":
        if not app.conf.logos_exe:
            app.exit("Cannot restore, Logos is not installed")
        dst_dir = Path(app.conf.logos_exe).parent
        # Remove existing data.
        for d in data_dirs:
            dst = Path(dst_dir) / d
            if dst.is_dir():
                shutil.rmtree(dst)
    else:  # backup mode
        timestamp = utils.get_timestamp().replace("-", "")
        current_backup_name = f"{app.conf.faithlife_product}{app.conf.faithlife_product_version}-{timestamp}"  # noqa: E501
        dst_dir = backup_dir / current_backup_name
        logging.debug(f'Backup directory path: "{dst_dir}".')

        # Check for existing backup.
        try:
            dst_dir.mkdir()
        except FileExistsError:
            # This shouldn't happen, there is a timestamp in the backup_dir name
            app.exit(f"Backup already exists: {dst_dir}.")

    # Verify disk space.
    if not utils.enough_disk_space(dst_dir, src_size):
        dst_dir.rmdir()
        app.exit(f"Not enough free disk space for {mode}.")

    # Run file transfer.
    if mode == "restore":
        m = f"Restoring backup from {str(source_dir_base)}…"
    else:
        m = f"Backing up to {str(dst_dir)}…"
    app.status(m)
    t = app.start_thread(copy_data, src_dirs, dst_dir)
    try:
        counter = 0
        while t.is_alive():
            logging.debug(f"DEV: Still copying… {counter}")
            counter = counter + 1
            time.sleep(1)
        print()
    except KeyboardInterrupt:
        print()
        app.exit("Cancelled with Ctrl+C.")
    t.join()
    app.status(f"Finished {mode}. {src_size} bytes copied to {str(dst_dir)}")


def copy_data(src_dirs, dst_dir):
    for src in src_dirs:
        shutil.copytree(src, Path(dst_dir) / src.name)


def remove_all_index_files(app: App):
    if not app.conf.logos_exe:
        app.exit("Cannot remove index files, Logos is not installed")
    logos_dir = os.path.dirname(app.conf.logos_exe)
    index_paths = [
        os.path.join(logos_dir, "Data", "*", "BibleIndex"),
        os.path.join(logos_dir, "Data", "*", "LibraryIndex"),
        os.path.join(logos_dir, "Data", "*", "PersonalBookIndex"),
        os.path.join(logos_dir, "Data", "*", "LibraryCatalog"),
    ]
    for index_path in index_paths:
        pattern = os.path.join(index_path, "*")
        files_to_remove = glob.glob(pattern)

        for file_to_remove in files_to_remove:
            try:
                os.remove(file_to_remove)
                logging.info(f"Removed: {file_to_remove}")
            except OSError as e:
                logging.error(f"Error removing {file_to_remove}: {e}")

    app.status("Removed all LogosBible index files!", 100)


def remove_library_catalog(app: App):
    if not app.conf.logos_exe:
        app.exit("Cannot remove library catalog, Logos is not installed")
    logos_dir = os.path.dirname(app.conf.logos_exe)
    files_to_remove = glob.glob(f"{logos_dir}/Data/*/LibraryCatalog/*")
    for file_to_remove in files_to_remove:
        try:
            os.remove(file_to_remove)
            logging.info(f"Removed: {file_to_remove}")
        except OSError as e:
            logging.error(f"Error removing {file_to_remove}: {e}")


def uninstall(app: App):
    """Completely uninstalls both this app and the installed product"""
    app.status("Uninstalling…")
    delete_paths = [
        app.conf.config_file_path,
        app.conf.install_dir,
    ]

    question = "Are you sure you want to uninstall?"
    context = (
        "We're about to run:\n\n"
        "rm -rf " + 
        " ".join(delete_paths)
    )
    if not app.approve(question, context):
        logging.debug("User refused to uninstall")
        return
    if app.approve(
        "Do you also want to clear the cache and logs?",
        "If you're debugging make sure you've already hit the \"Get Support\" button; "
        "we wouldn't want to lose those logs."
    ):
        delete_paths += [constants.CACHE_DIR, constants.STATE_DIR]

    for del_path in delete_paths:
        path = Path(del_path)
        if not path.exists():
            continue
        if path.is_file():
            os.remove(path)
        elif path.is_dir():
            shutil.rmtree(path)

    app.status("Uninstalled")

    app.conf.reload()


def get_support(app: App) -> str:
    """Creates a zip file with all the information to enable support and opens support
    """

    # Save in ~/Downloads or ~/
    output_dir = Path(os.path.expanduser("~/Downloads"))
    if not output_dir.exists():
        output_dir = output_dir.parent

    output_path = app.ask("Where do you want to save the support zip?", [
        str(output_dir / constants.DEFAULT_SUPPORT_FILE_NAME),
        constants.PROMPT_OPTION_NEW_FILE,
    ])

    app.status(f"Writing support package to: {output_path}", percent=0)

    if Path(output_path).exists():
        os.remove(output_path)

    with ZipFile(output_path, "x") as zip:
        if Path(app.conf.config_file_path).exists():
            zip.write(app.conf.config_file_path)
        if Path(app.conf.app_log_path).exists():
            zip.write(app.conf.app_log_path)
        if Path(app.conf.app_wine_log_path).exists():
            zip.write(app.conf.app_wine_log_path)
        if Path("/etc/os-release").exists():
            zip.write("/etc/os-release")
        run_commands = [
            ["glxinfo"],
            ["free", "-h"],
            ["inxi", "-F"],
            ["df", "-h"]
        ]

        if app.conf._raw.wine_binary:
            run_commands += [[app.conf._raw.wine_binary, "--version"]]

        subprocess_env = copy.deepcopy(os.environ)
        # Set LANG to enable support
        subprocess_env["LANG"] = "en_US.UTF-8"

        for command in run_commands:
            try:
                output = subprocess.check_output(
                    command,
                    text=True,
                    env=subprocess_env
                )
                # This writes to the root of the zip, which is file considering this is
                # just a support package
                zip.writestr(f"{command[0]}.out", output)
            except Exception as e:
                # Some of these commands may not be found.
                logging.debug(
                    "Failed to gather extra information: "
                    + " ".join(command) + ": " + str(e)
                )

        include_envs = [
            "WINEDEBUG",
            # Which desktop environment is running
            "XDG_CURRENT_DESKTOP",
            "DESKTOP_SESSION",
            # Needed to detect lxde
            "GDMSESSION",
            # Wayland vs X11
            "XDG_SESSION_TYPE",
            "DISPLAY",
            "LANG"
        ]

        context_to_write: dict[str, Any] = {}
        for env in include_envs:
            if os.getenv(env):
                context_to_write[env] = os.getenv(env)

        # Also add our DIALOG to the list
        context_to_write["DIALOG"] = system.get_dialog()

        # These aren't really envs, but still relevant. Consider a different file?
        context_to_write["RUNMODE"] = constants.RUNMODE
        context_to_write["CACHE_DIR"] = constants.CACHE_DIR
        context_to_write["DATA_HOME"] = constants.DATA_HOME
        context_to_write["CONFIG_DIR"] = constants.CONFIG_DIR
        context_to_write["STATE_DIR"] = constants.STATE_DIR

        context_to_write["network_cache"] = app.conf._network._cache._as_dict()
        context_to_write["ephemeral_config"] = app.conf._overrides.__dict__
        context_to_write["persistent_config"] = app.conf._raw._as_dict()

        zip.writestr("context.json", json.dumps(context_to_write, indent=4))

        app.status(f"Wrote support bundle to: {output_path}", percent=100)

        answer = app.ask(
            "How would you like to continue to get support?\n"
            f"Make sure to:\n"
            f"- Upload {output_path.replace(str(Path().home()), "~")}\n"
            "- Describe what went wrong\n"
            "- Describe actions you took",
            [
                'Launch Telegram',
                'Launch Matrix',
                'Open Github Issues',
                "Show links"
            ]
        )

        if answer == "Launch Telegram":
            webbrowser.open(constants.TELEGRAM_LINK)
        elif answer == "Launch Matrix":
            webbrowser.open(constants.MATRIX_LINK)
        elif answer == "Open Github Issues":
            webbrowser.open(constants.REPOSITORY_NEW_ISSUE_LINK)
        elif answer == "Show links":
            # Use app.info to show a dialog-friendly pop-up
            app.info(
                "Here are the links:\n"
                f"- Telegram: {constants.TELEGRAM_LINK}\n"
                f"- Matrix: {constants.MATRIX_LINK}\n"
                f"- Github Repository: {constants.REPOSITORY_LINK}\n"
                f"- Github Issues: {constants.REPOSITORY_NEW_ISSUE_LINK}\n"
            )

    return output_path