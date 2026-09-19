"""Work around black frames around Wine popups on wlroots-style Wayland compositors.

Wine >= 9.12 sets an XShape bounding mask, derived from the alpha channel, on
every per-pixel-alpha layered window (tooltips, menus, popups with drop shadows).
Compositors that do not apply XShape to XWayland surfaces -- Hyprland, Sway and
other wlroots-based ones -- then render the transparent shadow margin of every
such window as an opaque black frame.  GNOME (Mutter) and KDE (KWin) apply the
shape as a mask and are unaffected.

The fix is a tiny LD_PRELOAD shim (assets/nowineshape.c) that swallows just that
one X call.  It is compiled once with the system C compiler into the install
directory and prepended to LD_PRELOAD for every Wine process we start.

Set OUDEDETAI_XSHAPE_SHIM=1 or =0 to force it on or off.

Diagnosis and code by Claude (Anthropic); see the pull request that introduced
this module for the full analysis and the reproduction program.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import MutableMapping, Optional

from ou_dedetai import constants
from ou_dedetai.app import App

from . import system

SOURCE_NAME = "nowineshape.c"
LIBRARY_NAME = "nowineshape.so"

# Desktops known to honour XShape on XWayland windows.
_UNAFFECTED_DESKTOPS = ("gnome", "kde")

_build_failed = False


def wanted() -> bool:
    """Whether the current session is one where the shim helps."""
    forced = os.getenv("OUDEDETAI_XSHAPE_SHIM")
    if forced is not None:
        return forced.strip() not in ("", "0", "false", "no")
    if os.getenv("XDG_SESSION_TYPE", "").lower() != "wayland":
        return False
    desktop = os.getenv("XDG_CURRENT_DESKTOP", "").lower()
    return not any(name in desktop for name in _UNAFFECTED_DESKTOPS)


def library_path(app: App) -> Optional[str]:
    """Return the path of the built shim, building it first if needed.

    Returns None (and logs once) when it cannot be built, e.g. no C compiler.
    """
    global _build_failed
    if _build_failed:
        return None

    source = Path(constants.APP_ASSETS_DIR) / SOURCE_NAME
    target = Path(app.conf.install_dir) / "data" / LIBRARY_NAME

    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return str(target)

    compiler = next((c for c in (os.getenv("CC"), "cc", "gcc", "clang") if c and shutil.which(c)), None)
    if compiler is None:
        _build_failed = True
        logging.warning(
            f"No C compiler found to build {LIBRARY_NAME}; "
            "Wine popups may show black frames on this compositor."
        )
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    result = system.run_command(
        [compiler, "-O2", "-shared", "-fPIC", "-o", str(target), str(source), "-ldl"],
        check=False,
    )
    if result is None or result.returncode != 0:
        _build_failed = True
        stderr = result.stderr.strip() if result is not None else "no output"
        logging.warning(f"Failed to build {LIBRARY_NAME} with {compiler}: {stderr}")
        return None

    logging.info(f"Built {target} with {compiler}")
    return str(target)


def apply(env: MutableMapping[str, str], app: App) -> None:
    """Prepend the shim to LD_PRELOAD in env when it is wanted and available."""
    if not wanted():
        return
    path = library_path(app)
    if path is None:
        return
    current = env.get("LD_PRELOAD", "")
    if path in current.split(":"):
        return
    env["LD_PRELOAD"] = f"{path}:{current}" if current else path
