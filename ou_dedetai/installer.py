import logging
import os
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Optional

from ou_dedetai import system
from ou_dedetai.app import App, UserExitedFromAsk

from . import constants
from . import network
from . import utils
from . import wine


# This step doesn't do anything per-say, but "collects" all the choices in one step
# The app would continue to work without this function
def ensure_choices(app: App):
    app.installer_step_count += 1

    app.status("Asking questions if needed…")

    # Prompts (by nature of access and debug prints a number of choices the user has
    logging.debug(f"> {app.conf.faithlife_product=}")
    logging.debug(f"> {app.conf.faithlife_product_version=}")
    logging.debug(f"> {app.conf.faithlife_product_release=}")
    logging.debug(f"> {app.conf.install_dir=}")
    logging.debug(f"> {app.conf.installer_binary_dir=}")
    logging.debug(f"> {app.conf.wine_appimage_path=}")
    logging.debug(f"> {app.conf.wine_download_url=}")
    logging.debug(f"> {app.conf.wine_download_file_name=}")
    logging.debug(f"> {app.conf.wine_binary=}")
    logging.debug(f"> {app.conf.faithlife_product_icon_path}")
    logging.debug(f"> {app.conf.faithlife_installer_download_url}")
    # Debug print the entire config
    logging.debug(f"> Config={app.conf.__dict__}")

    app.status("Install is running…")


def ensure_install_dirs(app: App):
    app.installer_step_count += 1
    ensure_choices(app=app)
    app.installer_step += 1
    app.status("Ensuring installation directories…")
    wine_dir = Path("")

    bin_dir = Path(app.conf.installer_binary_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    logging.debug(f"> {bin_dir} exists?: {bin_dir.is_dir()}")

    logging.debug(f"> {app.conf.install_dir=}")
    logging.debug(f"> {app.conf.installer_binary_dir=}")

    wine_dir = Path(f"{app.conf.wine_prefix}")
    wine_dir.mkdir(parents=True, exist_ok=True)

    logging.debug(f"> {wine_dir} exists: {wine_dir.is_dir()}")
    logging.debug(f"> {app.conf.wine_prefix=}")


def ensure_sys_deps(app: App):
    app.installer_step_count += 1
    ensure_install_dirs(app=app)
    app.installer_step += 1
    app.status("Ensuring system dependencies are met…")

    if not app.conf.skip_install_system_dependencies:
        utils.install_dependencies(app)
        logging.debug("> Done.")
    else:
        logging.debug("> Skipped.")


# FIXME: consider where to put this long term - can  also be called in the update case
def setup_wine(app: App):
    """Do all the setup needed to get our wine executables ready

    This can be used both during installation and in the update case
    """
    downloaded_file = download_wine(app)

    # Extract if needed and update wine_binary
    if downloaded_file is not None and downloaded_file.name.lower().endswith(".appimage"):
        # Now replace the wine binary with the downloaded one
        app.conf.wine_binary = str(downloaded_file.absolute())
    elif downloaded_file is not None and downloaded_file.name.lower().endswith(".tar.gz"):
        # Do special handling for the extraction of the tarball.
        with tarfile.open(downloaded_file) as tarball:
            if Path(app.conf.wine_rootfs).exists():
                # Remove the directory tree before copying to ensure there are no leftovers from an earlier install
                shutil.rmtree(app.conf.wine_rootfs)
            # Make a new directory to be extracted into
            Path(app.conf.wine_rootfs).mkdir()
            tarball.extractall(app.conf.wine_rootfs)
        if not Path(app.conf.wine_path_in_rootfs).exists():
            raise Exception("Downloaded tarball didn't contain the needed wine binary")
        
        # Prepend the shebang
        with open(Path(app.conf.wine_rootfs) / "wrapper", 'r') as original:
            data = original.read()
        with open(Path(app.conf.wine_rootfs) / "wrapper", 'w') as modified:
            modified.write("#!/bin/bash\nAPPDIR=\"$(dirname -- \"${BASH_SOURCE[0]}\")\"\n" + data)

        app.conf.wine_binary = app.conf.wine_path_in_rootfs

    # Create symlinks to the new installation
    create_wine_symlinks(app)


def update_to_latest_wine(app: App):
    """Updates to the latest wine"""

    # This function takes advantage of the fact that we cache nearly everything.
    # It will always just redownload the latest (using caches where it can).
    # It DOES NOT compare versions like the previous implementation did.
    # This allows us to yank wine versions, then the update button will go back to our latest recommended
    # rather than doing nothing as the previous implementation did.
    if app.conf.wine_appimage_path is not None:
        app.conf.wine_binary = constants.RECOMMENDED_WINE_APPIMAGE_SIGIL
    elif app.conf.wine_binary.startswith(app.conf.wine_rootfs_relative):
        app.conf.wine_binary = constants.RECOMMENDED_WINE_TARBALL_SIGIL
    else:
        logging.debug("System wine detected - cowardly refusing to upgrade")
        return

    setup_wine(app)


# Have this as a separate function so we can upgrade wine to the latest version
def download_wine(app: App) -> Optional[Path]:
    if app.conf.faithlife_product_version != "9" and app.conf.wine_binary not in [
        constants.RECOMMENDED_WINE_APPIMAGE_SIGIL,
        constants.RECOMMENDED_WINE_TARBALL_SIGIL,
        constants.UNTESTED_WINE_STABLE_APPIMAGE_SIGIL,
        constants.UNTESTED_WINE_STAGING_APPIMAGE_SIGIL,
        constants.UNTESTED_WINE_DEVELOPMENT_APPIMAGE_SIGIL,
    ]:
        return None

    app.status("Ensuring wine is downloaded…")

    downloaded_file = None
    download_path = app.conf.wine_download_file_name  # noqa: E501
    filename = Path(download_path).name
    network.logos_reuse_download(
        app.conf.wine_download_url,
        filename,
        app.conf.download_dir,
        app=app,
    )
    downloaded_file = Path(f"{app.conf.download_dir}/{filename}")

    logging.debug(f"> File exists?: {downloaded_file}: {Path(downloaded_file).is_file()}")
    return downloaded_file


def ensure_wine_installed(app: App):
    app.installer_step_count += 1
    ensure_sys_deps(app=app)
    app.installer_step += 1

    app.status("Ensuring wine executables are available…")

    setup_wine(app=app)

    # PATH is modified if wine appimage isn't found, but it's not modified
    # during a restarted installation, so shutil.which doesn't find the
    # executables in that case.
    logging.debug(f"> {app.conf.wine_binary=}")
    logging.debug(f"> {app.conf.wine64_binary=}")
    logging.debug(f"> {app.conf.wineserver_binary=}")


def ensure_winetricks_executable(app: App):
    app.installer_step_count += 1
    ensure_wine_installed(app=app)
    app.installer_step += 1
    app.status("Ensuring winetricks executable is available…")

    system.ensure_winetricks(app=app)

    logging.debug(f"> {app.conf.winetricks_binary} is executable?: {os.access(app.conf.winetricks_binary, os.X_OK)}")


def ensure_product_installer_download(app: App):
    app.installer_step_count += 1
    ensure_winetricks_executable(app=app)
    app.installer_step += 1
    app.status(f"Ensuring {app.conf.faithlife_product} installer is downloaded…")

    downloaded_file = utils.get_downloaded_file_path(app.conf.download_dir, app.conf.faithlife_installer_name)
    if not downloaded_file:
        downloaded_file = Path(app.conf.download_dir) / app.conf.faithlife_installer_name
    network.logos_reuse_download(
        app.conf.faithlife_installer_download_url,
        app.conf.faithlife_installer_name,
        app.conf.download_dir,
        app=app,
    )
    # Copy file into install dir.
    installer = Path(f"{app.conf.install_dir}/data/{app.conf.faithlife_installer_name}")
    if not installer.is_file():
        shutil.copy(downloaded_file, installer.parent)

    logging.debug(f"> '{downloaded_file}' exists?: {Path(downloaded_file).is_file()}")


def ensure_wineprefix_init(app: App):
    app.installer_step_count += 1
    ensure_product_installer_download(app=app)
    app.installer_step += 1
    app.status("Ensuring wineprefix is initialized…")

    init_file = Path(f"{app.conf.wine_prefix}/system.reg")
    logging.debug(f"{init_file=}")
    if not init_file.is_file():
        logging.debug(f"{init_file} does not exist")
        logging.debug("Initializing wineprefix.")
        wine.initializeWineBottle(app.conf.wine64_binary, app)
        # wine.light_wineserver_wait()
        wine.wineserver_wait(app)
        logging.debug("Wine init complete.")
    logging.debug(f"> {init_file} exists?: {init_file.is_file()}")


def ensure_wineprefix_config(app: App):
    app.installer_step_count += 1
    ensure_wineprefix_init(app=app)
    app.installer_step += 1
    app.status("Ensuring wineprefix configuration…")

    # Force winemenubuilder.exe='' in registry.
    logging.debug("Setting wineprefix registry to ignore winemenubuilder.exe.")
    wine.disable_winemenubuilder(app=app, wine64_binary=app.conf.wine64_binary)

    # Force renderer=gdi in registry.
    logging.debug("Setting renderer=gdi in wineprefix registry.")
    wine.set_renderer(app=app, wine64_binary=app.conf.wine64_binary, value="gdi")

    # Force fontsmooth=rgb in registry.
    logging.debug("Setting fontsmoothing=rgb in wineprefix registry.")
    wine.set_fontsmoothing_to_rgb(app=app, wine64_binary=app.conf.wine64_binary)


def ensure_fonts(app: App):
    """Ensure the arial font is installed"""
    app.installer_step_count += 1
    ensure_wineprefix_config(app=app)
    app.installer_step += 1

    wine.install_fonts(app)


def ensure_icu_data_files(app: App):
    app.installer_step_count += 1
    ensure_fonts(app=app)
    app.installer_step += 1
    app.status("Ensuring ICU data files are installed…")
    logging.debug("- ICU data files")

    wine.enforce_icu_data_files(app=app)

    logging.debug("> ICU data files installed")


def ensure_product_installed(app: App):
    app.installer_step_count += 1
    ensure_icu_data_files(app=app)
    app.installer_step += 1
    app.status(f"Ensuring {app.conf.faithlife_product} is installed…")

    if not app.is_installed():
        # FIXME: Should we try to cleanup on a failed msi?
        # Like terminating msiexec if already running for Logos
        process = wine.install_msi(app)
        if process:
            process.wait()

    # Clear installed version cache
    app.conf._installed_faithlife_product_release = None

    # Clean up temp files, etc.
    utils.clean_all()

    logging.debug(f"> {app.conf.logos_exe=}")


def ensure_config_file(app: App):
    app.installer_step_count += 1
    ensure_product_installed(app=app)
    app.installer_step += 1
    app.status("Ensuring config file is up-to-date…")

    app.status("Install has finished.", 100)


def ensure_launcher_executable(app: App):
    app.installer_step_count += 1
    ensure_config_file(app=app)
    app.installer_step += 1
    if constants.RUNMODE == "binary":
        app.status(f"Copying launcher to {app.conf.install_dir}…")

        # Copy executable into install dir.
        launcher_exe = Path(f"{app.conf.install_dir}/{constants.BINARY_NAME}")
        if launcher_exe.is_file():
            logging.debug("Removing existing launcher binary.")
            launcher_exe.unlink()
        logging.info(f"Creating launcher binary by copying this installer binary to {launcher_exe}.")
        shutil.copy(sys.executable, launcher_exe)
        logging.debug(f"> File exists?: {launcher_exe}: {launcher_exe.is_file()}")
    else:
        app.status("Running from source. Skipping launcher copy.")


def ensure_launcher_shortcuts(app: App):
    app.installer_step_count += 1
    ensure_launcher_executable(app=app)
    app.installer_step += 1
    app.status("Creating launcher shortcuts…")
    if constants.RUNMODE == "binary":
        app.status("Creating launcher shortcuts…")
        create_launcher_shortcuts(app)
    else:
        # This is done so devs can run this without it clobbering their install
        app.status(
            f"Runmode is '{constants.RUNMODE}'. Won't create desktop shortcuts",
        )


def install(app: App):
    """Entrypoint for installing"""
    app.status("Installing…")
    try:
        ensure_launcher_shortcuts(app)
    except UserExitedFromAsk:
        # Reset choices, it's possible that the user didn't mean to select
        # one of the options they did - that is why they are exiting
        app.conf.faithlife_product = None  # type: ignore[assignment]
        app.conf.faithlife_product_version = None  # type: ignore[assignment]
        app.conf.faithlife_product_release = None  # type: ignore[assignment]
        app.conf.install_dir = None  # type: ignore[assignment]
        raise
    app.status("Install Complete!", 100)
    # Trigger a config update event to refresh the UIs
    app._config_updated_event.set()


def get_progress_pct(current, total):
    return round(current * 100 / total)


def create_wine_symlinks(app: App):
    app.status("Creating wine symlinks…")

    symlink_paths = ["wine", "wine64", "wineserver", "winetricks"]

    appdir_bindir = Path(app.conf.installer_binary_dir)
    # FIXME: This would only run once during install. Are we sure that's what we want?
    os.environ["PATH"] = f"{app.conf.installer_binary_dir}:{os.getenv('PATH')}"

    symlink_to: str

    if app.conf.wine_appimage_path is not None:
        # Ensure AppImage symlink.
        appimage_link = appdir_bindir / app.conf.wine_appimage_link_file_name

        # Only use the appimage_path if it exists
        # It may not exist if it was an old install's .appimage
        # where the install dir has been cleared.
        if app.conf.wine_appimage_path.exists():
            appimage_filename = app.conf.wine_appimage_path.name
        else:
            appimage_filename = app.conf.wine_download_file_name
        appimage_file = appdir_bindir / appimage_filename
        # Ensure appimage is copied to appdir_bindir.
        downloaded_file = utils.get_downloaded_file_path(app.conf.download_dir, appimage_filename)
        if downloaded_file is None:
            logging.critical("Failed to get a valid wine appimage")
            return
        if not appimage_file.exists():
            app.status(f"Copying: {downloaded_file} into: {appdir_bindir}")
            shutil.copy(downloaded_file, appdir_bindir)
        os.chmod(appimage_file, 0o755)
        app.conf.wine_appimage_path = appimage_file
        app.conf.wine_binary = str(appimage_file)

        appimage_link.unlink(missing_ok=True)  # remove & replace
        appimage_link.symlink_to(f"./{appimage_filename}")

        symlink_to = f"./{app.conf.wine_appimage_link_file_name}"
    elif (
        app.conf.wine_binary.startswith(app.conf.wine_rootfs)
        or app.conf.wine_binary.startswith(app.conf.wine_rootfs_relative)
    ):
        # FIXME: figure out what this script does and simplify
        symlink_to = str(Path(app.conf.wine_rootfs) / "wrapper")

        # Make symlinks in the rootfs in order for us to be able to detect where we are later.
        # FIXME: Consider switching this discovery to traversing symlinks instead
        for name in symlink_paths:
            p = Path(app.conf.wine_rootfs) /  name
            p.unlink(missing_ok=True)
            p.symlink_to(symlink_to)

        # Direct all wine commands here - it initializes the environment we need
        app.conf.wine_binary = str(Path(app.conf.wine_rootfs) / "wine")
    else:
        logging.debug("No need to make symlinks as the wine installation is from a binary")
        return

    # Ensure wine executables symlinks.
    for name in symlink_paths:
        p = appdir_bindir / name
        p.unlink(missing_ok=True)
        p.symlink_to(symlink_to)


def create_desktop_file(
    filename: str,
    app_name: str,
    generic_name: str,
    comment: str,
    exec_cmd: str,
    icon_path: str | Path,
    wm_class: str,
):
    contents = f"""[Desktop Entry]
Name={app_name}
GenericName={generic_name}
Comment={comment}
Exec={exec_cmd}
Icon={icon_path}
Terminal=false
Type=Application
StartupWMClass={wm_class}
Categories=Education;Spirituality;Languages;Literature;Maps;
Keywords=Logos;Verbum;FaithLife;Bible;Control;Christianity;Jesus;
"""
    local_share = Path.home() / ".local" / "share"
    xdg_data_home = Path(os.getenv("XDG_DATA_HOME", local_share))
    launcher_path = xdg_data_home / "applications" / filename
    if launcher_path.is_file():
        logging.info(f"Removing desktop launcher at {launcher_path}.")
        launcher_path.unlink()
    # Ensure the parent directory exists
    launcher_path.parent.mkdir(parents=True, exist_ok=True)

    logging.info(f"Creating desktop launcher at {launcher_path}.")
    with launcher_path.open("w") as f:
        f.write(contents)
    os.chmod(launcher_path, 0o755)
    return launcher_path


def create_launcher_shortcuts(app: App):
    # Set variables for use in launcher files.
    flproduct = app.conf.faithlife_product
    installdir = Path(app.conf.install_dir)
    logos_icon_src = constants.APP_IMAGE_DIR / f"{flproduct}-128-icon.png"
    app_icon_src = constants.APP_IMAGE_DIR / "icon.png"

    if not installdir.is_dir():
        app.exit("Can't create launchers because the installation folder does not exist.")
    app_dir = Path(installdir) / "data"
    logos_icon_path = app_dir / logos_icon_src.name
    app_icon_path = app_dir / app_icon_src.name

    if constants.RUNMODE == "binary":
        lli_executable = f"{installdir}/{constants.BINARY_NAME}"
    elif constants.RUNMODE == "source":
        script = Path(sys.argv[0]).expanduser().resolve()
        repo_dir = None
        for p in script.parents:
            for c in p.iterdir():
                if c.name == ".git":
                    repo_dir = p
                    break
        if repo_dir is None:
            app.exit("Could not find .git directory from arg 0")
        # Find python in virtual environment.
        py_bin = next(repo_dir.glob("*/bin/python"))
        if not py_bin.is_file():
            app.exit("Could not locate python binary in virtual environment.")
        lli_executable = f"env DIALOG=tk {py_bin} {script}"
    elif constants.RUNMODE in ["snap", "flatpak"]:
        logging.info(f"Not creating launcher shortcuts, {constants.RUNMODE} already handles this")
        return

    for src, path in [(app_icon_src, app_icon_path), (logos_icon_src, logos_icon_path)]:
        if not path.is_file():
            app_dir.mkdir(exist_ok=True)
            shutil.copy(src, path)
        else:
            logging.info(f"Icon found at {path}.")

    # Create Logos/Verbum desktop file.
    logos_path = create_desktop_file(
        f"{flproduct}Bible.desktop",
        f"{flproduct}",
        "Bible",
        "Runs Faithlife Bible Software via Wine (snap). Community supported.",
        f"{lli_executable} --run-installed-app",
        str(logos_icon_path),
        f"{flproduct.lower()}.exe",
    )
    logging.debug(f"> File exists?: {logos_path}: {logos_path.is_file()}")
    # Create Ou Dedetai desktop file.
    app_path = create_desktop_file(
        f"{constants.BINARY_NAME}.desktop",
        constants.APP_NAME,
        "FaithLife App Installer",
        "Installs and manages either Logos or Verbum via wine. Community supported.",
        lli_executable,
        str(app_icon_path),
        constants.BINARY_NAME,
    )
    logging.debug(f"> File exists?: {app_path}: {app_path.is_file()}")
