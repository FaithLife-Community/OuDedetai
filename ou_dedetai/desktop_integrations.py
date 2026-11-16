"""Optional desktop integrations for Logos (FaithLife-Community/logos-desktop-integrations).

On KDE Plasma these add KRunner commands, a "Look up in Logos" shortcut, reading-plan
reminders and desktop widgets. They are a separate project; this module only offers to
install them (once, and only on KDE Plasma) and runs their installer on request.
"""
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Mapping, Optional

import requests

from ou_dedetai import constants, network, system
from ou_dedetai.app import App

REPOSITORY = "FaithLife-Community/logos-desktop-integrations"
PROJECT_URL = f"https://github.com/{REPOSITORY}"


def is_kde_plasma(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when running in a KDE Plasma session."""
    env = os.environ if env is None else env
    desktops = env.get("XDG_CURRENT_DESKTOP", "").split(":")
    return any(d.strip().upper() == "KDE" for d in desktops) or env.get("KDE_FULL_SESSION") == "true"


def is_installed(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the integrations' backend is installed for this user."""
    env = os.environ if env is None else env
    data_home = Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return (data_home / "logos-plasma" / "logos_plasma.py").is_file()


def should_offer(app: App, env: Optional[Mapping[str, str]] = None) -> bool:
    """Offer once, interactively, on KDE Plasma, when Logos is installed and the
    integrations aren't."""
    return (
        not app.conf.desktop_integrations_offered
        and not app.conf._overrides.assume_yes  # never install something optional unasked
        and is_kde_plasma(env)
        and not is_installed(env)
        and app.is_installed()
    )


def offer(app: App) -> None:
    """Ask once whether to install the KDE Plasma integrations; install them if wanted."""
    if not should_offer(app):
        return
    # Record the offer first, so declining (or closing the prompt) means we don't ask again.
    app.conf.desktop_integrations_offered = True
    question = "Install the Logos integrations for KDE Plasma?"
    context = (
        "These add Logos commands to KRunner (Alt+Space), a shortcut to look up a copied Bible "
        "reference, reading-plan reminders, and Verse of the Day, Reading Plans and bookshelf "
        f"widgets. They're a separate FaithLife Community project: {PROJECT_URL}\n\n"
        f"You can install them later with: {constants.BINARY_NAME} --install-desktop-integrations"
    )
    if app.approve(question, context):
        install(app)


def latest_release_tag() -> str:
    data = network._net_get(f"https://api.github.com/repos/{REPOSITORY}/releases/latest")
    if data is None:
        raise RuntimeError(f"Couldn't look up the latest release of {REPOSITORY}")
    tag = json.loads(data.decode()).get("tag_name")
    if not tag:
        raise RuntimeError(f"No release found for {REPOSITORY}")
    return str(tag)


def install(app: App) -> bool:
    """Download the latest release and run its install.sh. Returns True on success."""
    if not is_kde_plasma():
        app.info("The Logos desktop integrations currently support KDE Plasma only.")
        return False
    try:
        tag = latest_release_tag()
        app.status(f"Downloading Logos desktop integrations {tag}…")
        archive = network._net_get(f"{PROJECT_URL}/archive/refs/tags/{tag}.tar.gz")
        if archive is None:
            raise RuntimeError("Download failed")
        with tempfile.TemporaryDirectory(prefix="logos-desktop-integrations-") as tmp:
            archive_path = Path(tmp) / "release.tar.gz"
            archive_path.write_bytes(archive)
            with tarfile.open(archive_path) as tar:
                tar.extractall(tmp, filter="data")
            installers = sorted(Path(tmp).glob("*/install.sh"))
            if not installers:
                raise RuntimeError("install.sh not found in the release")
            app.status("Installing Logos desktop integrations…")
            result = system.run_command(["sh", str(installers[0])], check=False, timeout=600,
                                        cwd=str(installers[0].parent))
    except (requests.RequestException, OSError, tarfile.TarError, subprocess.SubprocessError, RuntimeError) as e:
        logging.error(f"Installing desktop integrations failed: {e}")
        app.info(f"Couldn't install the Logos desktop integrations: {e}\n\nSee {PROJECT_URL}")
        return False

    output = ((result.stdout or "") + (result.stderr or "")).strip() if result else ""
    logging.info(f"Desktop integrations installer output:\n{output}")
    if result is None or result.returncode != 0:
        app.info("The Logos desktop integrations installer reported a problem:\n\n"
                 + "\n".join(output.splitlines()[-15:]))
        return False
    app.status("Logos desktop integrations installed.")
    if app.approve(
        "Restart the Plasma desktop now?",
        "The new widgets and search commands appear once Plasma reloads. Your panels and desktop "
        "will disappear for a few seconds and come back; open windows, including Logos, aren't affected.\n\n"
        "Afterwards try Alt+Space and type 'logos', or right-click the desktop → Add Widgets → search 'Logos'.",
    ):
        restart_plasma(app)
    else:
        app.status("Logos desktop integrations installed. They appear after you next log in.")
    return True


def restart_plasma(app: App) -> None:
    """Reload plasmashell (and KRunner) so new widgets and runners show up."""
    commands = [["systemctl", "--user", "restart", "plasma-plasmashell.service"]]
    if shutil.which("kquitapp6") and shutil.which("kstart"):
        commands.append(["sh", "-c", "kquitapp6 plasmashell; kstart plasmashell >/dev/null 2>&1"])
    for command in commands:
        try:
            if subprocess.run(command, capture_output=True, timeout=60).returncode == 0:
                break
        except (OSError, subprocess.SubprocessError) as error:
            logging.debug(f"{command}: {error}")
    else:
        app.status("Couldn't restart Plasma; log out and in to see the integrations.")
        return
    try:  # KRunner reloads its plugins when it next starts.
        subprocess.run(["kquitapp6", "krunner"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    app.status("Logos desktop integrations installed; Plasma reloaded.")


# ── Using the installed integrations from Ou Dedetai's own windows ───────────
#
# Ou Dedetai never reads Logos's databases for these features itself: it asks the
# integrations' backend, which owns that code (and its `logos_databases` switch).
# Each call returns an empty result when the integrations aren't installed, are an
# older version without the command, or have reading Logos's data switched off, so
# the window simply leaves the feature out.

def _backend(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    env = os.environ if env is None else env
    data_home = Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = data_home / "logos-plasma" / "logos_plasma.py"
    return path if path.is_file() else None


def _run_backend(*args: str, timeout: int = 60) -> Optional[str]:
    backend = _backend()
    python = "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else "python3"
    if backend is None:
        return None
    # The backend runs on the system's Python, not the one bundled in our binary.
    env = system.fix_ld_library_path(dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1"))
    try:
        result = subprocess.run([python, str(backend), *args], capture_output=True, text=True,
                                timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError) as error:
        logging.debug(f"Desktop integrations {args}: {error}")
        return None
    if result.returncode != 0:
        logging.debug(f"Desktop integrations {args}: exit {result.returncode}: {result.stderr.strip()}")
        return None
    return result.stdout


def _json(*args: str, timeout: int = 60):
    out = _run_backend(*args, timeout=timeout)
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def logos_data_enabled() -> bool:
    """Whether the integrations may read Logos's databases (their `logos_databases` setting)."""
    sources = _json("--data-sources", timeout=20)
    return bool(isinstance(sources, dict) and sources.get("logos_databases"))


def reading_plans() -> list[dict]:
    """Today's reading-plan entries, as the Reading Plans widget shows them."""
    plans = _json("--reading-plans")
    return [p for p in plans if isinstance(p, dict)] if isinstance(plans, list) else []


def saved_layouts() -> list[str]:
    names = _json("--layouts", "--json", timeout=30)
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def open_layout(name: str) -> bool:
    """Load a saved layout in the running Logos (COM LoadLayout, a few seconds)."""
    return _run_backend("--layout", name, timeout=180) is not None


def open_url(url: str) -> bool:
    """Open a Logos link (logosres:, logosref:, logos4:) without a terminal."""
    return _run_backend("--open", url, timeout=60) is not None


def open_reference(text: str) -> bool:
    """Open a typed Bible reference in the preferred Bible."""
    return _run_backend("--reference", text, timeout=120) is not None


def todays_reading() -> Optional[dict]:
    """The first reading due from your reading plans: {"title", "label", "url"}, or None."""
    for plan in reading_plans():
        for reading in plan.get("readings") or []:
            if isinstance(reading, dict) and reading.get("url"):
                return {"title": plan.get("title", ""), "label": reading.get("label", ""),
                        "url": reading["url"]}
    return None
