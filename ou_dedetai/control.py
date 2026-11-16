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


def leftover_wine(prefix: str | None) -> list[int]:
    """PIDs of Wine processes still running in this prefix."""
    import psutil  # type: ignore[import-untyped]
    if not prefix:
        return []
    want = str(Path(prefix).resolve())
    pids = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = (process.info["name"] or "").lower()
            if not (name.startswith("wine") or name.endswith(".exe")):
                continue
            env_prefix = process.environ().get("WINEPREFIX")
            if env_prefix and str(Path(env_prefix).resolve()) == want:
                pids.append(process.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            pass
    return pids


def _kill(pids: list[int]) -> None:
    import psutil
    processes = []
    for pid in pids:
        try:
            process = psutil.Process(pid)
            process.kill()
            processes.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(processes, timeout=10)


# Desktop entries and URL handlers create_launcher_shortcuts writes.
URL_SCHEMES = ("x-scheme-handler/logos4", "x-scheme-handler/libronixdls")


def _raw_paths(app: App) -> tuple[Path | None, Path | None]:
    """install_dir and our Wine prefix inside it, straight from the config file (never prompts).

    A prefix given with WINEPREFIX isn't ours to delete (it may be shared), so it isn't returned."""
    raw = app.conf._raw
    if not raw.install_dir:
        return None, None
    install_dir = Path(raw.install_dir).expanduser()
    return install_dir, install_dir / "data" / "wine64_bottle"


def purge_targets(app: App) -> list[Path]:
    """Everything Ou Dedetai and its Logos/Verbum install put on this computer."""
    install_dir, prefix = _raw_paths(app)
    applications = Path(constants.XDG_DATA_HOME) / "applications"
    targets = [
        install_dir, prefix,
        Path(app.conf.config_file_path).expanduser(),
        Path(constants.CONFIG_DIR).expanduser(),
        Path(constants.CACHE_DIR).expanduser(),
        Path(constants.STATE_DIR).expanduser(),
        Path(constants.DATA_HOME).expanduser() / constants.BINARY_NAME,  # default install_dir
        applications / f"{constants.BINARY_NAME}.desktop",
    ]
    for product in ("Logos", "Verbum"):
        targets += [applications / f"{product}Bible.desktop", applications / f"{product}-url-handler.desktop"]
    seen: list[Path] = []
    for target in targets:
        if target is None or not target.exists() or target in seen:
            continue
        # Skip anything already inside another target.
        if any(parent in seen for parent in target.parents):
            continue
        seen = [s for s in seen if target not in s.parents] + [target]
    return seen


def _forget_url_handlers() -> None:
    """Drop our logos4:/libronixdls: defaults from mimeapps.list."""
    config_home = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    for mimeapps in (config_home / "mimeapps.list",
                     Path(constants.XDG_DATA_HOME) / "applications" / "mimeapps.list"):
        try:
            lines = mimeapps.read_text().splitlines(keepends=True)
        except FileNotFoundError:
            continue
        kept = [line for line in lines if line.split("=", 1)[0].strip() not in URL_SCHEMES]
        if kept != lines:
            mimeapps.write_text("".join(kept))
    if shutil.which("update-desktop-database"):
        try:
            system.run_command(["update-desktop-database", str(Path(constants.XDG_DATA_HOME) / "applications")])
        except (OSError, subprocess.CalledProcessError) as e:
            logging.warning(f"Couldn't refresh the desktop database: {e}")


def _purge_akousousin(app: App) -> None:
    """Akousousin removes itself (voices, models, settings, its Wine registration)."""
    launcher = system.akousousin_launcher()
    if not launcher.is_file():
        return
    try:
        help_text = subprocess.run([str(launcher), "--help"], capture_output=True, text=True, timeout=60).stdout
        if "--purge" not in help_text:
            app.status("This Akousousin is too old to remove itself; update it first, then run akousousin --purge.")
            return
        result = subprocess.run([str(launcher), "--purge", "--yes"], capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logging.warning(f"akousousin --purge: {result.stdout}{result.stderr}")
            app.status("Akousousin couldn't remove everything; see the log.")
    except (OSError, subprocess.SubprocessError) as e:
        logging.warning(f"Couldn't run akousousin --purge: {e}")


def _purge_integrations() -> None:
    from ou_dedetai import desktop_integrations
    if not desktop_integrations.is_installed():
        return
    script = Path(constants.XDG_DATA_HOME) / "logos-plasma" / "uninstall.sh"
    try:
        subprocess.run(["sh", str(script)], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        logging.warning(f"Couldn't run the desktop integrations' uninstaller: {e}")
    config_home = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    shutil.rmtree(Path(constants.XDG_DATA_HOME) / "logos-plasma", ignore_errors=True)
    shutil.rmtree(config_home / "logos-plasma", ignore_errors=True)


PURGE_WARNING = (
    "This deletes {product} and its Wine folder, including anything in it that hasn't synced "
    "to Faithlife (downloaded books, offline notes, local settings), plus all of Ou Dedetai's "
    "settings, logs, cache and shortcuts. It can't be undone. Make a backup first if you're unsure."
)


def purge(app: App) -> bool:
    """Remove everything Ou Dedetai put on this computer, as if it was never installed.

    Asks first (warning of data loss), then whether to remove Akousousin and the
    desktop integrations too. Returns True if anything was removed."""
    from ou_dedetai import desktop_integrations
    product = app.conf._raw.faithlife_product or "Logos"
    targets = purge_targets(app)
    context = PURGE_WARNING.format(product=product) + "\n\nWe'll remove:\n" + "\n".join(f"  {t}" for t in targets)
    if not app.approve("Remove everything?", context):
        logging.debug("User refused to purge")
        return False
    with_aks = system.akousousin_installed() and app.approve(
        "Also remove Akousousin?", "This deletes Akousousin with its voices, speech models and settings.")
    with_integrations = desktop_integrations.is_installed() and app.approve(
        "Also remove the Logos desktop integrations?", "The search shortcuts, widgets and their settings.")

    app.status("Stopping Wine…")
    _, prefix = _raw_paths(app)
    _kill(leftover_wine(app.conf._overrides.wine_prefix or (str(prefix) if prefix else None)))
    if with_aks:
        app.status("Removing Akousousin…")
        _purge_akousousin(app)
    if with_integrations:
        app.status("Removing the desktop integrations…")
        _purge_integrations()

    app.status("Removing files…")
    failed = []
    for path in targets:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError as e:
            logging.error(f"Couldn't remove {path}: {e}")
            failed.append(str(path))
    try:
        Path(constants.DATA_HOME).expanduser().rmdir()  # only if nothing else is in it
    except OSError:
        pass
    _forget_url_handlers()
    if failed:
        app.status("Some files couldn't be removed: " + ", ".join(failed))
    else:
        app.status("Removed")
    app.conf.reload()
    return True


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

        try:
            from . import wine_settings
            zip.writestr("wine-settings.txt", wine_settings.format_report(
                wine_settings.report_for_app(app), wine_settings.renderer_summary(app)
            ))
        except Exception:
            logging.exception("Failed to add the Wine settings report to the support package")

        if Path("/etc/os-release").exists():
            zip.write("/etc/os-release")
        run_commands = [
            ["glxinfo"],
            ["free", "-h"],
            ["inxi", "-F"],
            ["df", "-h"],
            ["xdg-mime", "query", "default", "x-scheme-handler/https"],
            ["xdg-mime", "query", "default", "x-scheme-handler/logos4"],
            ["xdg-mime", "query", "default", "x-scheme-handler/libronixdls"]
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
                zip.writestr(f"/tmp/{" ".join(command).replace("/","_")}", output)
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