"""Optional desktop integrations for Logos (FaithLife-Community/logos-desktop-integrations).

On KDE Plasma these add KRunner commands, a "Look up in Logos" shortcut, reading-plan
reminders and desktop widgets; on GNOME, search in the Activities overview, the shortcut
and reminders. They are a separate project; this module only offers to install them
(once, on a supported desktop), notices newer releases, and runs their installer on request.
"""
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping, Optional

import requests

from ou_dedetai import constants, network, system, utils
from ou_dedetai.app import App

REPOSITORY = "FaithLife-Community/logos-desktop-integrations"
PROJECT_URL = f"https://github.com/{REPOSITORY}"


def is_kde_plasma(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when running in a KDE Plasma session."""
    env = os.environ if env is None else env
    desktops = env.get("XDG_CURRENT_DESKTOP", "").split(":")
    return any(d.strip().upper() == "KDE" for d in desktops) or env.get("KDE_FULL_SESSION") == "true"


def is_gnome(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when running in a GNOME session (including Ubuntu's)."""
    env = os.environ if env is None else env
    return any(d.strip().upper() == "GNOME" for d in env.get("XDG_CURRENT_DESKTOP", "").split(":"))


def desktop(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """"plasma", "gnome", or None when the integrations don't support this desktop."""
    return "plasma" if is_kde_plasma(env) else "gnome" if is_gnome(env) else None


def _install_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """Where the integrations install themselves (they kept their first name, logos-plasma)."""
    env = os.environ if env is None else env
    return Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "logos-plasma"


def _backend(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    path = _install_dir(env) / "logos_plasma.py"
    return path if path.is_file() else None


def is_installed(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the integrations' backend is installed for this user."""
    return _backend(env) is not None


def installed_version(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The installed release ("0.5.2"), "0" for installs older than v0.5.1 (which didn't
    record it), or None when they aren't installed."""
    if not is_installed(env):
        return None
    try:
        return (_install_dir(env) / "VERSION").read_text().strip().lstrip("v") or "0"
    except OSError:
        return "0"


def update_available(app: App) -> Optional[str]:
    """The latest release's version if it's newer than the installed one, else None.

    Uses the shared release cache (renewed every 12 hours), like Ou Dedetai's other update
    checks; Troubleshooting → Check for updates now renews it at once."""
    current = installed_version()
    if current is None or desktop() is None or network.is_offline():
        return None
    try:
        latest = str(app.conf._network._repo_version(REPOSITORY, tag="latest").version).lstrip("v")
    except (requests.RequestException, OSError, ValueError, LookupError, RuntimeError) as e:
        logging.debug(f"Desktop integrations update check failed: {e}")
        return None
    return latest if utils.is_newer_version(latest, current) else None


def should_offer(app: App, env: Optional[Mapping[str, str]] = None) -> bool:
    """Offer once, interactively, on KDE Plasma or GNOME, when Logos is installed and
    the integrations aren't."""
    return (
        not app.conf.desktop_integrations_offered
        and not app.conf._overrides.assume_yes  # never install something optional unasked
        and desktop(env) is not None
        and not is_installed(env)
        and app.is_installed()
    )


def offer(app: App) -> None:
    """Ask once whether to install the desktop integrations; install them if wanted."""
    if not should_offer(app):
        return
    # Record the offer first, so declining (or closing the prompt) means we don't ask again.
    app.conf.desktop_integrations_offered = True
    if desktop() == "plasma":
        question = "Install the Logos integrations for KDE Plasma?"
        features = ("Logos commands in KRunner (Alt+Space), a shortcut to look up a copied Bible "
                    "reference, reading-plan reminders, and Verse of the Day, Reading Plans and "
                    "bookshelf widgets")
    else:
        question = "Install the Logos integrations for GNOME?"
        features = ("Logos in the Activities overview search, a shortcut to look up a copied Bible "
                    "reference, and reading-plan reminders")
    context = (
        f"These add {features}. They're a separate FaithLife Community project: {PROJECT_URL}\n\n"
        f"You can install them later with: {constants.BINARY_NAME} --install-desktop-integrations"
    )
    if app.approve(question, context):
        install(app)


def offer_or_notice_update(app: App) -> None:
    """For the TUI: the one-time install offer, or a status line when an update is out."""
    if should_offer(app):
        offer(app)
    elif newer := update_available(app):
        app.status(f"Logos desktop integrations {newer} is available: "
                   "choose Update Desktop Integrations in the menu.")


def install(app: App) -> bool:
    """Download the latest release and run its install.sh. Returns True on success."""
    session = desktop()
    if session is None:
        app.info("The Logos desktop integrations support KDE Plasma and GNOME.")
        return False
    try:
        # The release has no attached files: its source archive is the download.
        release = network._get_release_data(REPOSITORY, tag="latest")
        with tempfile.TemporaryDirectory(prefix="logos-desktop-integrations-") as tmp:
            archive = Path(tmp) / "release.tar.gz"
            network._net_get(release.download_url, target=archive, app=app)
            if not archive.is_file() or archive.stat().st_size == 0:
                raise RuntimeError("the download failed")
            utils.untar_file(archive, tmp)
            installers = sorted(Path(tmp).glob("*/install.sh"))
            if not installers:
                raise RuntimeError("install.sh not found in the release")
            app.status("Installing Logos desktop integrations…")
            result = system.run_program(["sh", str(installers[0]), f"--{session}"], timeout=600,
                                        cwd=installers[0].parent)
            if result is None:
                raise RuntimeError("its installer couldn't be started")
    except (requests.RequestException, OSError, LookupError, ValueError, RuntimeError) as e:
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
    system.offer_wl_clipboard(app)
    if session == "gnome":
        # GNOME Shell reads search providers only when it starts.
        app.info("Logos desktop integrations installed. Log out and back in once, then search "
                 "for a Bible reference or 'logos' in the Activities overview.")
        return True
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
    # run_program, so plasmashell starts with the system's Qt, not the copy in our binary.
    for command in commands:
        result = system.run_program(command, timeout=60)
        if result is not None and result.returncode == 0:
            break
    else:
        app.status("Couldn't restart Plasma; log out and in to see the integrations.")
        return
    system.run_program(["kquitapp6", "krunner"], timeout=30)  # KRunner reloads its plugins when it next starts
    app.status("Logos desktop integrations installed; Plasma reloaded.")


# ── Using the installed integrations from Ou Dedetai's own windows ───────────
#
# Ou Dedetai never reads Logos's databases for these features itself: it asks the
# integrations' backend, which owns that code (and its `logos_databases` switch).
# Each call returns an empty result when the integrations aren't installed, are an
# older version without the command, or have reading Logos's data switched off, so
# the window simply leaves the feature out.

def _run_backend(*args: str, timeout: int = 60) -> Optional[str]:
    backend = _backend()
    if backend is None:
        return None
    # The backend runs on the system's Python, not the one bundled in our binary.
    python = "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else "python3"
    result = system.run_program([python, str(backend), *args], timeout=timeout)
    if result is None:
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
