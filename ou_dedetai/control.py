"""These functions take no arguments by default.
They can be called from CLI, GUI, or TUI.
"""

import copy
import glob
import json
import logging
import os
import shutil
from pathlib import Path
import subprocess
from typing import Any
import webbrowser
from zipfile import ZipFile

from ou_dedetai import constants
from ou_dedetai import system
from ou_dedetai.app import App


def edit_file(config_file: str):
    system.run_command(["xdg-open", config_file])


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
    ]
    # Only add install_dir if we know what it is
    if app.conf._raw.install_dir is not None:
        delete_paths += [app.conf._raw.install_dir]

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
        if Path(app.conf.app_wine_log_previous_path).exists():
            zip.write(app.conf.app_wine_log_previous_path)
        # Only include LogosCrash.log for now. Logos.log can include
        # information about which books the user owns which is more information than
        # The user would probably expect to be included in a support package.
        if (
            app.conf._faithlife_crash_log is not None and
            Path(app.conf._faithlife_crash_log).exists()
        ):
            zip.write(app.conf._faithlife_crash_log)

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
            "Make sure to:\n"
            f"- Check the pinned issues {constants.REPOSITORY_ISSUES_LINK} to see if your problem is already known.\n"
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