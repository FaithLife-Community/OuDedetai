from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def get_runmode() -> str:
    """Gets the executing envoirnment
    
    Returns:
        flatpak or snap or binary (pyinstaller) or script
    """
    if os.environ.get("container") == "flatpak":
        return 'flatpak'
    elif getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return 'binary'
    elif os.environ.get('SNAP'):
        return 'snap'
    else:
        return 'script'


# Are we running from binary or src?
RUNMODE = get_runmode()
_snap = os.environ.get('SNAP')
if hasattr(sys, '_MEIPASS'):
    BUNDLE_DIR = Path(sys._MEIPASS)
elif _snap is not None:
    BUNDLE_DIR = Path(_snap)
else:
    # We are running in normal development mode
    BUNDLE_DIR = Path(__file__).resolve().parent
del(_snap)

# Now define assets and img directories.
APP_IMAGE_DIR = BUNDLE_DIR / 'img'
APP_ASSETS_DIR = BUNDLE_DIR / 'assets'

# Define app name variables.
APP_NAME = 'Ou Dedetai'
BINARY_NAME = 'oudedetai'
PACKAGE_NAME = 'ou_dedetai'
REPO_NAME = 'OuDedetai'

REPOSITORY_LINK = f"https://github.com/FaithLife-Community/{REPO_NAME}"
WIKI_LINK = f"{REPOSITORY_LINK}/wiki"
REPOSITORY_ISSUES_LINK = f"{REPOSITORY_LINK}/issues"
REPOSITORY_NEW_ISSUE_LINK = f"{REPOSITORY_LINK}/issues/new"
TELEGRAM_LINK = "https://t.me/linux_logos"
MATRIX_LINK = "https://matrix.to/#/#logosbible:matrix.org"

CACHE_LIFETIME_HOURS = 12
"""How long to wait before considering our version cache invalid"""

if RUNMODE == 'snap':
    _snap_user_common = os.getenv('SNAP_USER_COMMON')
    if _snap_user_common is None:
        raise ValueError("SNAP_USER_COMMON environment MUST exist when running a snap.")
    CACHE_DIR = str(Path(_snap_user_common) / '.cache' / 'FaithLife-Community')
    del _snap_user_common
else:
    CACHE_DIR = str(Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache' / 'FaithLife-Community'))) 

XDG_DATA_HOME = str(Path(os.getenv('XDG_DATA_HOME', str(Path.home() / '.local/share'))))
XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
DATA_HOME = str(Path(XDG_DATA_HOME)/ 'FaithLife-Community') 
CONFIG_DIR = os.getenv("XDG_CONFIG_HOME", "~/.config") + "/FaithLife-Community"
STATE_DIR = os.getenv("XDG_STATE_HOME", "~/.local/state") + "/FaithLife-Community"

# Set other run-time variables not set in the env.
DEFAULT_CONFIG_PATH = os.path.expanduser(f"{CONFIG_DIR}/{BINARY_NAME}.json")
DEFAULT_APP_WINE_LOG_PATH = os.path.expanduser(f"{STATE_DIR}/wine.log")
DEFAULT_APP_LOG_PATH = os.path.expanduser(f"{STATE_DIR}/{BINARY_NAME}.log")
NETWORK_CACHE_PATH = f"{CACHE_DIR}/network.json"

RELATIVE_BINARY_DIR = "data/bin"
RELATIVE_WINE_DISTRIBUTION_DIR = f"{RELATIVE_BINARY_DIR}/wine-distribution"

DEFAULT_WINEDEBUG = "err+all"
LEGACY_CONFIG_FILES = [
    # If the user didn't have XDG_CONFIG_HOME set before, but now does.
    os.path.expanduser("~/.config/FaithLife-Community/oudedetai"),
    os.path.expanduser("~/.config/FaithLife-Community/Logos_on_Linux.json"),
    os.path.expanduser("~/.config/Logos_on_Linux/Logos_on_Linux.json"),
    os.path.expanduser("~/.config/Logos_on_Linux/Logos_on_Linux.conf")
]
LLI_AUTHOR = "Ferion11, John Goodman, T. H. Wright, N. Marti, N. Shaaban"
# The next branch: its builds are development versions of the release after beta 16. Published
# test builds (prereleases) are 4.0.0-beta.17.devN: newer than beta 16, older than beta 17.
LLI_CURRENT_VERSION = "4.0.0-beta.17.dev9"
# This SHOULD match the version of winetricks we ship in the latest appimage
WINETRICKS_VERSION = '20250102'
DEFAULT_LOG_LEVEL = logging.WARNING
LOGOS_BLUE = '#0082FF'
LOGOS_GRAY = '#E7E7E7'
LOGOS_WHITE = '#FCFCFC'
PID_FILE = f'/tmp/{BINARY_NAME}.pid'

WINE_BETA_SIGIL = "Experimental (AKA Beta)"
# System packages during install: off while we test whether the bundled Wine tarball
# needs any (it ran fine on Bazzite without them). OUDEDETAI_INSTALL_DEPS=1 brings the
# old behaviour back; "Install dependencies" in Troubleshooting / --install-dependencies
# still installs them on request.
INSTALL_SYSTEM_PACKAGES = os.getenv("OUDEDETAI_INSTALL_DEPS") == "1"

WINE_RECOMMENDED_SIGIL = "Recommended"
WINE_RECOMMENDED_APPIMAGE_SIGIL= "Recommended Appimage"
WINE_RECOMMENDED_TARBALL_SIGIL= "Recommended Bundled"
WINE_UNTESTED_STABLE_APPIMAGE_SIGIL= "Latest Appimage from wine stable (untested)"
WINE_UNTESTED_STAGING_APPIMAGE_SIGIL= "Latest Appimage from wine staging (untested)"
WINE_UNTESTED_DEVELOPMENT_APPIMAGE_SIGIL= "Latest Appimage from wine development (untested)"

FAITHLIFE_PRODUCTS = ["Logos", "Verbum"]
FAITHLIFE_PRODUCT_VERSIONS = ["10"] # This used to include 9

SUPPORT_MESSAGE = f"""If you need help, please consult:
{WIKI_LINK}
If the install failed, use the \"Get Support\" operation
"""

DEFAULT_SUPPORT_FILE_NAME = "FaithlifeCommunitySupport.zip"

# Strings for choosing a follow up file or directory
PROMPT_OPTION_DIRECTORY = "Choose Directory"
PROMPT_OPTION_FILE = "Choose File"
PROMPT_OPTION_NEW_FILE = "Save as"

PROMPT_OPTION_SIGILS = [PROMPT_OPTION_DIRECTORY, PROMPT_OPTION_FILE, PROMPT_OPTION_NEW_FILE] 

# String for when a binary is meant to be downloaded later
DOWNLOAD = "Download"
WINDOWS_VERSIONS = ["vista", "win7", "win8", "win10", "win11", "Return to Main Menu"]

# Registry keys Ou Dedetai reads and sets in the prefix, under HKEY_CURRENT_USER.
REG_LOGOS_LOGGING = "Software\\Logos4\\Logging"
REG_WINE_MSI = "Software\\Wine\\MSI"
REG_WINE_MEDIA_FOUNDATION = "Software\\Wine\\MediaFoundation"
REG_WINE_APP_DEFAULTS = "Software\\Wine\\AppDefaults"
REG_WINE_DIRECT3D = "Software\\Wine\\Direct3D"
REG_WINE_DLL_OVERRIDES = "Software\\Wine\\DllOverrides"
REG_WINE_FONT_REPLACEMENTS = "Software\\Wine\\Fonts\\Replacements"

# Desktop entries and URL handlers create_launcher_shortcuts writes.
URL_SCHEMES = ("x-scheme-handler/logos4", "x-scheme-handler/libronixdls")

AKOUSOUSIN_TARBALL = "Akousousin-Linux-x86_64.tar.gz"
# The wl-paste Akousousin bundles (the integrations use it when the system has none).
AKOUSOUSIN_WL_PASTE = Path.home() / ".local/lib/akousousin/resources/helpers/wl-paste/bin/wl-paste"
