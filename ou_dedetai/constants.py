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
TELEGRAM_LINK = "https://t.me/linux_logos"
MATRIX_LINK = "https://matrix.to/#/#logosbible:matrix.org"

CACHE_LIFETIME_HOURS = 12
"""How long to wait before considering our version cache invalid"""

if RUNMODE == 'snap':
    _snap_user_common = os.getenv('SNAP_USER_COMMON')
    if _snap_user_common is None:
        raise ValueError("SNAP_USER_COMMON environment MUST exist when running a snap.")
    CACHE_DIR = Path(_snap_user_common) / '.cache' / 'FaithLife-Community'
    del _snap_user_common
else:
    CACHE_DIR = Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache' / 'FaithLife-Community')) #noqa: E501

XDG_DATA_HOME = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local/share' / 'FaithLife-Community'))
CONFIG_DIR = os.getenv("XDG_CONFIG_HOME", "~/.config") + "/FaithLife-Community"
STATE_DIR = os.getenv("XDG_STATE_HOME", "~/.local/state") + "/FaithLife-Community"

# Set other run-time variables not set in the env.
DEFAULT_CONFIG_PATH = os.path.expanduser(f"{CONFIG_DIR}/{BINARY_NAME}.json")
DEFAULT_APP_WINE_LOG_PATH = os.path.expanduser(f"{STATE_DIR}/wine.log")
DEFAULT_APP_LOG_PATH = os.path.expanduser(f"{STATE_DIR}/{BINARY_NAME}.log")
NETWORK_CACHE_PATH = f"{CACHE_DIR}/network.json"
DEFAULT_WINEDEBUG = "fixme+all,err+all"
LEGACY_CONFIG_FILES = [
    # If the user didn't have XDG_CONFIG_HOME set before, but now does.
    os.path.expanduser("~/.config/FaithLife-Community/oudedetai"),
    os.path.expanduser("~/.config/FaithLife-Community/Logos_on_Linux.json"),
    os.path.expanduser("~/.config/Logos_on_Linux/Logos_on_Linux.json"),
    os.path.expanduser("~/.config/Logos_on_Linux/Logos_on_Linux.conf")
]
LLI_AUTHOR = "Ferion11, John Goodman, T. H. Wright, N. Marti, N. Shaaban"
LLI_CURRENT_VERSION = "4.0.0-beta.8"
DEFAULT_LOG_LEVEL = logging.WARNING
LOGOS_BLUE = '#0082FF'
LOGOS_GRAY = '#E7E7E7'
LOGOS_WHITE = '#FCFCFC'
PID_FILE = f'/tmp/{BINARY_NAME}.pid'

FAITHLIFE_PRODUCTS = ["Logos", "Verbum"]
FAITHLIFE_PRODUCT_VERSIONS = ["10", "9"]

SUPPORT_MESSAGE = f"If you need help, please consult:\n{WIKI_LINK}\nIf that doesn't answer your question, please send the following files {DEFAULT_CONFIG_PATH}, {DEFAULT_APP_WINE_LOG_PATH} and {DEFAULT_APP_LOG_PATH} to one of the following group chats:\nTelegram: {TELEGRAM_LINK}\nMatrix: {MATRIX_LINK}"  # noqa: E501

# Strings for choosing a follow up file or directory
PROMPT_OPTION_DIRECTORY = "Choose Directory"
PROMPT_OPTION_FILE = "Choose File"

# String for when a binary is meant to be downloaded later
DOWNLOAD = "Download"
