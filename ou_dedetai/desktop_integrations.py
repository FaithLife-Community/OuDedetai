"""Optional desktop integrations for Logos (FaithLife-Community/logos-desktop-integrations).

On KDE Plasma these add KRunner commands, a "Look up in Logos" shortcut, reading-plan
reminders and desktop widgets; on GNOME, the same commands in the Activities overview search,
the shortcut and the reminders. They are a separate project; this module only offers to
install them (once, and only on those desktops) and runs their installer on request.
"""
import json
import logging
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Mapping, Optional

from ou_dedetai import constants, network, system
from ou_dedetai.app import App

REPOSITORY = "FaithLife-Community/logos-desktop-integrations"
PROJECT_URL = f"https://github.com/{REPOSITORY}"

PLASMA = "plasma"
GNOME = "gnome"
# The first release whose installer supports GNOME (and takes --plasma / --gnome)
FIRST_GNOME_RELEASE = (0, 5, 0)

DESKTOP_NAMES = {PLASMA: "KDE Plasma", GNOME: "GNOME"}


def supported_desktop(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """PLASMA or GNOME when running in one of those sessions, else None."""
    env = os.environ if env is None else env
    desktops = [d.strip().upper() for d in env.get("XDG_CURRENT_DESKTOP", "").split(":")]
    if "KDE" in desktops or env.get("KDE_FULL_SESSION") == "true":
        return PLASMA
    if "GNOME" in desktops:
        return GNOME
    return None


def release_version(tag: str) -> tuple[int, ...]:
    """Turn a tag like "v0.5.0" into (0, 5, 0); a tag with no numbers counts as (0,)."""
    numbers = re.findall(r"\d+", tag)
    return tuple(int(n) for n in numbers[:3]) if numbers else (0,)


def release_supports(tag: str, desktop: str) -> bool:
    """Whether the release's installer supports this desktop."""
    return desktop == PLASMA or release_version(tag) >= FIRST_GNOME_RELEASE


def is_installed(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the integrations' backend is installed for this user."""
    env = os.environ if env is None else env
    data_home = Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return (data_home / "logos-plasma" / "logos_plasma.py").is_file()


def should_offer(app: App, env: Optional[Mapping[str, str]] = None) -> bool:
    """Offer once, interactively, on KDE Plasma or GNOME, when Logos is installed and the
    integrations aren't."""
    return (
        not app.conf.desktop_integrations_offered
        and not app.conf._overrides.assume_yes  # never install something optional unasked
        and supported_desktop(env) is not None
        and not is_installed(env)
        and app.is_installed()
    )


def offer(app: App) -> None:
    """Ask once whether to install the integrations for this desktop; install them if wanted."""
    if not should_offer(app):
        return
    desktop = supported_desktop()
    assert desktop is not None
    if desktop == GNOME:
        # GNOME support arrived in a later release: until it's out, don't ask (and don't
        # record the offer), so GNOME users are asked once it is.
        try:
            if not release_supports(latest_release_tag(), GNOME):
                return
        except Exception as e:
            logging.debug(f"Not offering desktop integrations: {e}")
            return
    # Record the offer first, so declining (or closing the prompt) means we don't ask again.
    app.conf.desktop_integrations_offered = True
    question = f"Install the Logos integrations for {DESKTOP_NAMES[desktop]}?"
    if desktop == PLASMA:
        what = ("These add Logos commands to KRunner (Alt+Space), a shortcut to look up a Bible "
                "reference you've selected or copied, reading-plan reminders, and Verse of the Day, "
                "Reading Plans and bookshelf widgets.")
    else:
        what = ("These let you open passages, search, copy verses and more from the Activities "
                "overview search, add a shortcut to look up a Bible reference you've selected or "
                "copied, and send reading-plan reminders.")
    context = (
        f"{what} They're a separate FaithLife Community project: {PROJECT_URL}\n\n"
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
    desktop = supported_desktop()
    if desktop is None:
        app.info("The Logos desktop integrations support KDE Plasma and GNOME, "
                 "and neither seems to be running.")
        return False
    try:
        tag = latest_release_tag()
        if not release_supports(tag, desktop):
            app.info(f"The latest release of the Logos desktop integrations ({tag}) doesn't support "
                     f"{DESKTOP_NAMES[desktop]} yet. See {PROJECT_URL}")
            return False
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
            command = ["sh", str(installers[0])]
            if release_version(tag) >= FIRST_GNOME_RELEASE:
                command.append(f"--{desktop}")  # older installers take no options
            result = system.run_command(command, check=False, timeout=600,
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
    if desktop == PLASMA:
        hint = "Try Alt+Space and type 'logos', or right-click the desktop → Add Widgets → search 'Logos'."
    else:
        hint = ("Log out and back in once, then press Super and type 'logos'. "
                "Alt+Shift+L looks up a reference you've selected or copied.")
    app.info(f"Logos desktop integrations installed.\n\n{hint}")
    return True
