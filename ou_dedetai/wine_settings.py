"""The Wine settings Ou Dedetai applies to a Logos prefix, described in one place.

Each entry says what a setting is for and how to recognise it in the prefix's
registry files, so every interface can show what is set and why (GUI Settings
page, ``--show-wine-config``, the support report). Applying the settings is still
done by ``installer.apply_wine_config`` and the functions it calls in ``wine``.

Reading is done from ``user.reg``/``system.reg`` directly: it needs no Wine process,
so it is fast and safe while Logos is running.
"""
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from ou_dedetai.app import App

from . import wine


class Group(str, Enum):
    NEEDED = "needed"
    REVIEW = "review"
    NOT_NEEDED = "not-needed"


class State(str, Enum):
    APPLIED = "applied"
    DIFFERENT = "different"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegCheck:
    """One registry value to look for. ``key`` is relative to HKCU unless ``hklm``."""
    key: str
    name: str
    # Predicate on the raw value text as Wine stores it (e.g. '"native"', 'dword:00000001').
    matches: Callable[[str], bool]
    expected: str
    hklm: bool = False


@dataclass(frozen=True)
class WineSetting:
    id: str
    title: str
    reason: str
    checks: tuple[RegCheck, ...]
    group: Group = Group.NEEDED
    link: Optional[str] = None
    # Whether this Wine build needs the setting at all; None means always.
    needed_with: Optional[Callable[["SettingsContext"], bool]] = None


@dataclass
class SettingsContext:
    oinos: bool


@dataclass
class SettingReport:
    setting: WineSetting
    state: State
    needed: bool
    details: list[str] = field(default_factory=list)


def _string(value: str) -> Callable[[str], bool]:
    return lambda raw: raw.strip().lower() == f'"{value}"'.lower()


def _dword(value: int) -> Callable[[str], bool]:
    return lambda raw: raw.strip().lower() == f"dword:{value:08x}"


def _contains(text: str) -> Callable[[str], bool]:
    return lambda raw: text.lower() in raw.lower()


def _present(raw: str) -> bool:
    return True


_DLL = "Software\\Wine\\DllOverrides"

SETTINGS: tuple[WineSetting, ...] = (
    WineSetting(
        id="printing",
        title="Printing through GDI",
        reason="WPF's XPS print path isn't in Wine; this makes Logos print through GDI to CUPS.",
        checks=(RegCheck(
            "Software\\Microsoft\\.NETFramework\\Windows Presentation Foundation\\Printing",
            "DisableXPSOMPrinting", _dword(1), "1"),),
    ),
    WineSetting(
        id="icu",
        title="Language data (ICU)",
        reason="Uses the installed ICU files so Logos doesn't crash listing cultures.",
        link="https://bugs.winehq.org/show_bug.cgi?id=58805",
        checks=tuple(RegCheck(_DLL, dll, _string("native"), "native") for dll in ("icu", "icuin", "icuuc")),
    ),
    WineSetting(
        id="font-replacements",
        title="Font replacements",
        reason="Maps Windows fonts Logos expects to open fonts; print preview crashes without them.",
        checks=tuple(
            RegCheck("Software\\Wine\\Fonts\\Replacements", family, _present, ", ".join(subs))
            for family, subs in wine.FONT_REPLACEMENTS.items()
        ),
    ),
    WineSetting(
        id="no-wine-menus",
        title="No Wine menu entries",
        reason="Ou Dedetai makes its own shortcuts; Wine's would duplicate them and take over file types.",
        checks=(RegCheck(_DLL, "winemenubuilder.exe", _string(""), "disabled"),),
    ),
    WineSetting(
        id="logos-self-update",
        title="Logos can update itself",
        reason="Lets Logos's own updates finish under this Wine instead of failing part-way.",
        checks=(RegCheck("Software\\Wine\\MSI", "IgnoreFailedActions",
                         _contains(wine.LOGOS_IGNORED_MSI_ACTIONS[0]), wine.LOGOS_IGNORED_MSI_ACTIONS[0]),),
        needed_with=lambda ctx: ctx.oinos,
    ),
    WineSetting(
        id="font-smoothing",
        title="Font smoothing (RGB)",
        reason="Subpixel text smoothing. No reason was recorded when it was added; may be removed.",
        group=Group.REVIEW,
        checks=(RegCheck("Control Panel\\Desktop", "FontSmoothingType", _dword(2), "2 (RGB)"),),
    ),
    WineSetting(
        id="xpsprint-off",
        title="xpsprint turned off",
        reason="Stops WPF using Wine's XPS print stubs. Our oinos builds remove the stubs, so it isn't needed there.",
        checks=(RegCheck(_DLL, "xpsprint", _string(""), "disabled"),),
        needed_with=lambda ctx: not ctx.oinos,
    ),
)


_SECTION_RE = re.compile(r"^\[(?P<key>[^\]]+)\][^\n]*\n(?P<body>.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)
_VALUE_RE = re.compile(r'^"(?P<name>(?:[^"\\]|\\.)*)"=(?P<value>.*)$', re.MULTILINE)


def parse_reg_file(path: Path) -> dict[str, dict[str, str]]:
    """Parse a Wine registry file into {lower-case key: {lower-case value name: raw value}}.

    Keys are as Wine writes them in the file (relative to the hive, single backslashes)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    result: dict[str, dict[str, str]] = {}
    for section in _SECTION_RE.finditer(text):
        key = section.group("key").replace("\\\\", "\\").lower()
        values = result.setdefault(key, {})
        for match in _VALUE_RE.finditer(section.group("body")):
            name = match.group("name").replace("\\\\", "\\").lower()
            values[name] = match.group("value")
    return result


def configured_wine_binary(app: App) -> Optional[str]:
    """The Wine binary from the saved config, without asking the user for one."""
    raw = app.conf._raw.wine_binary
    if not raw:
        return None
    if not Path(raw).exists() and app.conf._raw.install_dir:
        candidate = Path(app.conf._raw.install_dir) / raw
        if candidate.exists():
            return str(candidate)
    return raw


def wine_release(app: App) -> Optional["wine.WineRelease"]:
    binary = configured_wine_binary(app)
    if binary is None:
        return None
    try:
        release, _ = wine.get_wine_release(binary)
        return release
    except Exception:
        logging.debug("Couldn't read the Wine release", exc_info=True)
        return None


def _context(app: App) -> SettingsContext:
    release = wine_release(app)
    return SettingsContext(oinos=bool(release and wine.wine_supports_logos_updates(release)))


def report(
    prefix: Path,
    context: SettingsContext,
    settings: tuple[WineSetting, ...] = SETTINGS,
) -> list[SettingReport]:
    """What each setting looks like in the prefix at ``prefix``."""
    user = parse_reg_file(prefix / "user.reg")
    system = parse_reg_file(prefix / "system.reg")
    reports = []
    for setting in settings:
        needed = setting.needed_with(context) if setting.needed_with else True
        if not user and not system:
            reports.append(SettingReport(setting, State.UNKNOWN, needed))
            continue
        found, wrong, details = 0, 0, []
        for check in setting.checks:
            hive = system if check.hklm else user
            raw = hive.get(check.key.lower(), {}).get(check.name.lower())
            if raw is None:
                details.append(f"{check.name}: not set (expected {check.expected})")
            elif check.matches(raw):
                found += 1
            else:
                wrong += 1
                details.append(f"{check.name}: {raw} (expected {check.expected})")
        if found == len(setting.checks):
            state = State.APPLIED
        elif wrong:
            state = State.DIFFERENT
        else:
            state = State.MISSING
        reports.append(SettingReport(setting, state, needed, details))
    return reports


def report_for_app(app: App) -> list[SettingReport]:
    # Only from saved values: reading the report must never prompt the user.
    if not app.conf._raw.install_dir and not app.conf._overrides.wine_prefix:
        return []
    return report(Path(app.conf.wine_prefix), _context(app))


def renderer_summary(app: App) -> str:
    """The renderer in use, e.g. "dxvk", "gl" or "gdi"; "default" when nothing is set."""
    if not app.conf._raw.install_dir and not app.conf._overrides.wine_prefix:
        return "unknown"
    try:
        return wine.get_effective_renderer(app) or "default"
    except Exception:
        return "unknown"


def format_report(reports: list[SettingReport], renderer: Optional[str] = None) -> str:
    """Plain-text table for the CLI and support report."""
    if not reports:
        return "No Wine prefix found."
    lines = []
    labels = {
        Group.NEEDED: "Needed for Logos",
        Group.REVIEW: "Being reviewed",
        Group.NOT_NEEDED: "Not needed",
    }
    for group in Group:
        rows = [r for r in reports if r.setting.group == group]
        if not rows:
            continue
        lines.append(labels[group])
        for r in rows:
            state = r.state.value if r.needed else f"{r.state.value}, not needed with this Wine"
            lines.append(f"  [{state}] {r.setting.title}: {r.setting.reason}")
            for detail in r.details:
                lines.append(f"      {detail}")
        lines.append("")
    if renderer:
        lines.append(f"Renderer: {renderer}")
    return "\n".join(lines).rstrip() + "\n"
