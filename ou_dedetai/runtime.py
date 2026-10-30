"""Select the Wine runtime before or after installation, independently of the UI."""
import logging
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from typing import cast

from ou_dedetai import constants, system, utils, wine
from ou_dedetai.app import App, UserExitedFromAsk


def _managed_dir(app: App) -> Path | None:
    """The install's Wine directory, or None while the install dir is still undecided.

    Never prompts: choosing Wine before installing must not ask install questions."""
    conf = app.conf
    if conf._overrides.installer_binary_dir is None and not (conf._overrides.install_dir or conf._raw.install_dir):
        return None
    return Path(conf.installer_binary_dir)


def discover_runtimes(app: App) -> dict[str, list[Path]]:
    managed = _managed_dir(app)
    images = [] if managed is None else sorted(
        p for p in managed.glob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() == '.appimage')
    local = set()
    for directory in os.get_exec_path() + [str(Path.home() / 'bin'), '/usr/local/bin']:
        for name in ('wine', 'wine64'):
            path = Path(directory) / name
            if (path.is_file() and os.access(path, os.X_OK)
                    and (managed is None or path.parent.resolve() != managed.resolve())):
                local.add(path.absolute())
    steam_roots = [Path.home() / '.steam/steam', Path.home() / '.local/share/Steam',
                   Path.home() / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
    libraries = set(steam_roots)
    for root in steam_roots:
        manifest = root / 'steamapps/libraryfolders.vdf'
        if manifest.is_file():
            libraries.update(Path(p.replace('\\\\', '\\')) for p in
                             re.findall(r'"path"\s+"([^"]+)"', manifest.read_text()))
    proton = set()
    for root in libraries:
        builds = list((root / 'steamapps/common').glob('Proton*'))
        builds += list((root / 'compatibilitytools.d').glob('*'))
        for build in builds:
            for layout in ('files/bin', 'dist/bin'):
                for name in ('wine', 'wine64'):
                    path = build / layout / name
                    if path.is_file() and os.access(path, os.X_OK):
                        proton.add(path.absolute())
    return {'Installed AppImages': images, 'System/local Wine': sorted(local - proton),
            'Local Proton': sorted(proton)}


def _ensure_stopped(app: App) -> None:
    from ou_dedetai.logos import State
    if app.logos.logos_state in (State.STARTING, State.STOPPING) or app.logos.indexing_state in (
        State.STARTING, State.STOPPING
    ):
        raise ValueError('Wait for Logos and its indexer to stop before changing Wine.')
    if app.is_installed():
        app.logos.get_logos_pids()
    if any(p.is_running() for group in app.logos.existing_processes.values() for p in group):
        raise ValueError('Stop Logos and its indexer before changing Wine.')


def _check_version(app: App, binary: Path) -> None:
    result = subprocess.run([str(binary), '--version'], capture_output=True, text=True,
                            timeout=15, env=system.fix_ld_library_path(None))
    if result.returncode != 0:
        raise ValueError(f'Cannot run {binary}: {result.stderr.strip()}')
    match = re.search(r'wine-(\d+)\.(\d+)', result.stdout, re.IGNORECASE)
    if match:
        major, minor = map(int, match.groups())
        release = wine.WineRelease(major, minor, 'staging' if 'staging' in result.stdout.lower()
                                   else ('stable' if minor == 0 else 'devel'))
        target_release = (app.conf.installed_faithlife_product_release if app.is_installed()
                          else app.conf._raw.faithlife_product_release)
        target_version = app.conf._raw.faithlife_product_version or constants.FAITHLIFE_PRODUCT_VERSIONS[0]
        allowed, reason = wine.check_wine_rules(release, target_release, target_version)
        if allowed and major in (7, 8, 9, 10):
            return
        warning = reason if not allowed else 'This Wine version is not covered by the current compatibility rules.'
    else:
        warning = 'This runtime reports an unrecognised Wine version.'
    if not app.approve(f'{warning}\n{result.stdout.strip()}\nUse this developer runtime anyway?'):
        raise UserExitedFromAsk


def _server_for(binary: Path) -> Path | None:
    for path in (binary.parent / 'wineserver', binary.parent / 'server/wineserver',
                 binary.parent.parent / 'server/wineserver'):
        if path.is_file() and os.access(path, os.X_OK):
            return path.absolute()
    return None


def activate_runtime(app: App, selected: Path, server: Path | None = None) -> None:
    """Validate first; restore runtime links if saving the selection fails."""
    _ensure_stopped(app)
    selected = selected.expanduser().absolute()
    if not selected.is_file():
        raise ValueError(f'Wine runtime does not exist: {selected}')
    managed = Path(app.conf.installer_binary_dir)
    is_image = selected.suffix.lower() == '.appimage'
    snapshots: dict[Path, str | None] = {}
    created_image = None
    old_mode = None
    try:
        if is_image:
            if not utils.check_appimage(selected):
                raise ValueError(f'Not a supported AppImage: {selected}')
            managed.mkdir(parents=True, exist_ok=True)
            if selected.name == app.conf.wine_appimage_link_file_name:
                raise ValueError("Choose the versioned AppImage file, not the selected-runtime symlink.")
            destination = managed / selected.name
            if selected != destination:
                if destination.exists() or destination.is_symlink():
                    # Do not overwrite an existing runtime with a same-named download.
                    raise ValueError(f'{destination} already exists. '
                                     'Select that installed AppImage or rename the download.')
                created_image = destination
                shutil.copy2(selected, destination)
            selected = destination
            old_mode = selected.stat().st_mode
            selected.chmod(old_mode | 0o100)
            server = managed / 'wineserver'
        else:
            if not os.access(selected, os.X_OK):
                raise ValueError(f'Wine executable is not executable: {selected}')
            server = server or _server_for(selected)
            if server is None:
                raise ValueError('Cannot locate the matching wineserver; select it explicitly.')
            server = server.expanduser().absolute()
            if not server.is_file() or not os.access(server, os.X_OK):
                raise ValueError(f'wineserver is not executable: {server}')
        _check_version(app, selected)
        _ensure_stopped(app)
        if is_image:
            targets = {managed / app.conf.wine_appimage_link_file_name: './' + selected.name}
            targets.update({managed / name: './' + app.conf.wine_appimage_link_file_name
                            for name in ('wine', 'wine64', 'wineserver', 'winetricks')})
            for link in targets:
                if link.exists() and not link.is_symlink():
                    raise ValueError(f'Refusing to replace a non-symlink runtime file: {link}')
            for link, target in targets.items():
                snapshots[link] = os.readlink(link) if link.is_symlink() else None
                with tempfile.TemporaryDirectory(dir=managed) as temporary:
                    replacement = Path(temporary) / 'link'
                    replacement.symlink_to(target)
                    os.replace(replacement, link)
        assert server is not None
        app.conf.select_wine_runtime(str(selected), str(server), 'AppImage' if is_image else 'Custom')
    except BaseException:
        for link, previous in snapshots.items():
            link.unlink(missing_ok=True)
            if previous is not None:
                link.symlink_to(previous)
        if created_image is not None:
            created_image.unlink(missing_ok=True)
        elif old_mode is not None:
            selected.chmod(old_mode)
        raise
    app.status(f'Selected Wine runtime: {selected}', 100)


@dataclass
class RuntimeOption:
    name: str
    path: Path | None
    current: bool = False
    recommended: bool = False
    version: str | None = None
    server: Path | None = None
    download_url: str | None = None
    prerelease: bool = False

    @property
    def label(self) -> str:
        label = self.name
        if self.path is None:
            return label + ' (not found)'
        if self.version is not None:
            label += f' — {self.version}'
        if self.prerelease:
            label += ' (pre-release)'
        if self.recommended:
            label += ' (recommended)'
        if self.current:
            label += ' (current)'
        if self.download_url and not self.path.is_file():
            label += ' (download required)'
        return f'{label} — {self.path}'


def _current_path(app: App) -> Path | None:
    """The configured runtime as a path, without prompting for the install dir."""
    selected = app.conf._raw.wine_binary
    if not selected or selected in (constants.WINE_RECOMMENDED_SIGIL, constants.WINE_BETA_SIGIL):
        return None
    if Path(selected).is_absolute():
        return Path(selected).expanduser().absolute()
    managed = _managed_dir(app)
    if managed is None:
        # A release chosen before installing; the installer downloads it here.
        return Path(app.conf.download_dir) / Path(selected).name
    return Path(app.conf.wine_binary).expanduser().absolute()


def runtime_options(app: App) -> list[RuntimeOption]:
    """Build the combined list without running binaries or fetching metadata."""
    found = discover_runtimes(app)
    current = _current_path(app)
    options = []
    for category, paths in found.items():
        name = 'Local Wine' if category == 'System/local Wine' else 'Local Proton'
        if not paths and category != 'Installed AppImages':
            options.append(RuntimeOption(name, None))
        for path in paths:
            if category == 'Installed AppImages':
                title = path.name
            elif category == 'Local Proton':
                title = f'Local Proton: {path.parents[2].name}'
            else:
                title = name
            options.append(RuntimeOption(title, path, current=path == current))
    if current is not None and not any(option.current for option in options):
        title = current.name if current.suffix.lower() == '.appimage' else 'Custom Wine'
        options.append(RuntimeOption(title, current, current=True))
    # A custom wineserver previously selected by the user may live elsewhere.
    for option in options:
        if option.current and app.conf._raw.wine_server:
            option.server = Path(app.conf._raw.wine_server)
            if not option.server.is_absolute() and _managed_dir(app) is not None:
                option.server = Path(app.conf.wineserver_binary)
    return sorted(options, key=lambda option: not option.current)


def runtime_version(path: Path) -> str:
    """A display-only probe; inability to run is distinct from not found."""
    try:
        result = subprocess.run([str(path), '--version'], capture_output=True, text=True,
                                timeout=3, env=system.fix_ld_library_path(None))
        if result.returncode == 0 and result.stdout.strip():
            return ' '.join(result.stdout.split())
    except (OSError, subprocess.SubprocessError):
        pass
    return 'version unknown'


def recommended_appimage(app: App) -> tuple[str, str] | None:
    try:
        from ou_dedetai import installer
        return installer.appimage_for_channel(app, installer.default_wine_channel())
    except Exception:
        logging.warning('Unable to retrieve recommended Wine version', exc_info=True)
        return None


def recommended_name(app: App) -> str | None:
    release = recommended_appimage(app)
    return release[0] if release else None


@dataclass(frozen=True)
class AppImageRelease:
    name: str
    url: str
    prerelease: bool = False


def available_appimages(app: App) -> list[AppImageRelease]:
    """The latest stable and pre-release AppImages offered for download.

    A pre-release only exists while the newest wine-appimages release is
    still marked as one; once a maintainer promotes it, it becomes the latest
    stable release instead."""
    releases = []
    try:
        releases.append(AppImageRelease(app.conf.wine_appimage_recommended_file_name,
                                        app.conf.wine_appimage_recommended_url))
    except Exception:
        logging.warning('Unable to retrieve the latest Wine AppImage release', exc_info=True)
    try:
        name, url = app.conf.wine_appimage_beta_file_name, app.conf.wine_appimage_beta_url
        if name is not None and url is not None:
            releases.append(AppImageRelease(name, url, prerelease=True))
    except Exception:
        logging.warning('Unable to retrieve the Wine AppImage pre-release', exc_info=True)
    return releases


def _include_download(app: App, options: list[RuntimeOption], name: str, url: str) -> list[RuntimeOption]:
    """Add a downloadable AppImage unless it is already listed; return the matching options."""
    matches = [option for option in options if option.path is not None and option.path.name == name]
    if not matches:
        # Before installing, show where the installer will download it.
        directory = _managed_dir(app) or Path(app.conf.download_dir)
        option = RuntimeOption(name, directory / name)
        options.append(option)
        matches = [option]
    for option in matches:
        option.download_url = url
    return matches


def include_recommended(app: App, options: list[RuntimeOption], release: tuple[str, str] | None) -> None:
    """Include the installer recommendation even when it needs downloading."""
    if release is None:
        return
    for option in _include_download(app, options, *release):
        option.recommended = True


def include_releases(app: App, options: list[RuntimeOption], releases: list[AppImageRelease]) -> None:
    """Offer the published stable and pre-release AppImages, downloading on selection."""
    for release in releases:
        for option in _include_download(app, options, release.name, release.url):
            option.prerelease = option.prerelease or release.prerelease


class _RuntimeDownloadApp:
    """Convert an installer download failure into a recoverable picker error."""
    def __init__(self, app: App):
        self.app = app

    def __getattr__(self, name):
        return getattr(self.app, name)

    def exit(self, reason: str, intended: bool = False):
        raise ValueError(reason)


def choose_for_install(app: App, option: RuntimeOption, server: Path | None = None) -> None:
    """Before installing, only record the choice; the installer does the rest.

    Published releases are stored the way the installer's own prompt stores them,
    so it downloads, verifies, copies and links them as usual. Local runtimes are
    checked (with the usual compatibility warning) but not copied."""
    path = option.path
    if path is None:
        raise ValueError('This runtime was not found.')
    if option.download_url:
        app.conf.choose_wine_for_install(f'{constants.RELATIVE_BINARY_DIR}/{path.name}')
    else:
        path = path.expanduser().absolute()
        if not path.is_file():
            raise ValueError(f'Wine runtime does not exist: {path}')
        if path.suffix.lower() == '.appimage':
            if not utils.check_appimage(path):
                raise ValueError(f'Not a supported AppImage: {path}')
        else:
            if not os.access(path, os.X_OK):
                raise ValueError(f'Wine executable is not executable: {path}')
            server = server or option.server or _server_for(path)
            if server is None:
                raise ValueError('Cannot locate the matching wineserver; select it explicitly.')
        # Downloaded AppImages usually aren't executable yet; the installer makes
        # its copy executable, and changing Wine after installing checks it then.
        if os.access(path, os.X_OK):
            _check_version(app, path)
        app.conf.choose_wine_for_install(str(path), None if server is None else str(server.expanduser().absolute()))
    app.status(f'Wine runtime for installation: {path.name}', 100)


def activate_option(app: App, option: RuntimeOption, server: Path | None = None) -> None:
    if not app.is_installed():
        choose_for_install(app, option, server)
        return
    if option.path is None:
        raise ValueError('This runtime was not found.')
    selected = option.path
    if option.download_url and not selected.is_file():
        from ou_dedetai import installer
        _ensure_stopped(app)
        selected = installer.download_appimage(cast(App, _RuntimeDownloadApp(app)), selected.name,
                                               option.download_url)
    activate_runtime(app, selected, server or option.server)


def added_runtime(path: Path) -> RuntimeOption:
    """Check a candidate without copying it or changing the active runtime."""
    path = path.expanduser().absolute()
    if not path.is_file():
        raise ValueError(f'Wine runtime does not exist: {path}')
    if path.suffix.lower() == '.appimage':
        if not utils.check_appimage(path):
            raise ValueError(f'Not a supported AppImage: {path}')
        return RuntimeOption(path.name, path)
    if not os.access(path, os.X_OK):
        raise ValueError(f'Wine executable is not executable: {path}')
    return RuntimeOption('Custom Wine', path, server=_server_for(path))


def selection_lock(app: App) -> threading.Lock:
    # Shared by the installer and every picker so only one can change Wine at a time.
    if not hasattr(app, '_wine_selection_lock'):
        setattr(app, '_wine_selection_lock', threading.Lock())
    lock: threading.Lock = getattr(app, '_wine_selection_lock')
    return lock


def downloads_directory() -> Path:
    downloads = Path.home() / 'Downloads'
    return downloads if downloads.is_dir() else Path.home()


def select_runtime(app: App) -> None:
    """Combined menu for text frontends; a chosen file is activated immediately."""
    with selection_lock(app):
        try:
            options = runtime_options(app)
            release = recommended_appimage(app)
            recommended = release[0] if release else None
            include_releases(app, options, available_appimages(app))
            include_recommended(app, options, release)
            for option in options:
                if option.path:
                    option.recommended = option.path.name == recommended
                    if option.path.suffix.lower() != '.appimage':
                        option.version = runtime_version(option.path)
            while True:
                labels = {option.label: option for option in options if option.path is not None}
                missing = '\n'.join(option.label for option in options if option.path is None)
                current = next((option.label for option in options if option.current), None)
                choice = app.choose_runtime('Select Wine runtime\n' + missing, [*labels, 'Add new…'], current)
                if choice in ('Cancel', 'Return to Main Menu'):
                    return
                try:
                    if choice == 'Add new…':
                        option = added_runtime(Path(app.choose_file(
                            'Choose an AppImage or Wine executable',
                            initial_dir=downloads_directory(), appimages=True)))
                        assert option.path is not None
                        if option.path.suffix.lower() != '.appimage':
                            option.version = runtime_version(option.path)
                            if option.server is None:
                                option.server = Path(app.choose_file('Choose the matching wineserver executable',
                                                                    initial_dir=option.path.parent))
                        option.recommended = option.path.name == recommended
                    else:
                        option = labels[choice]
                        if option.current:
                            return
                    path = option.path
                    assert path is not None
                    server = option.server
                    if path.suffix.lower() != '.appimage' and server is None:
                        server = _server_for(path)
                        if server is None:
                            server = Path(app.choose_file('Choose the matching wineserver executable',
                                                          initial_dir=path.parent))
                    activate_option(app, option, server)
                    return
                except UserExitedFromAsk:
                    continue
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    app.info(f'Wine selection failed: {error}')
        except UserExitedFromAsk:
            return
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            logging.exception('Wine selection failed')
            app.info(f'Wine selection failed: {error}')
