"""Optional desktop integrations for Logos (FaithLife-Community/logos-desktop-integrations).

On KDE Plasma these add KRunner commands, a "Look up in Logos" shortcut, reading-plan
reminders and desktop widgets. They are a separate project; this module only offers to
install them (once, and only on KDE Plasma) and runs their installer on request.
"""
import json
import logging
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Mapping, Optional

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
    except Exception as e:
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
    app.info("Logos desktop integrations installed.\n\n"
             "Try Alt+Space and type 'logos', or right-click the desktop → Add Widgets → search 'Logos'.")
    return True
