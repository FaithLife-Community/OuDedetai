import logging
import os
import shutil
import subprocess
import sys
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
    logging.debug(f"> {app.conf.wine_appimage_recommended_url=}")
    logging.debug(f"> {app.conf.wine_appimage_recommended_file_name=}")
    logging.debug(f"> {app.conf.wine_binary_code=}")
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


def check_for_known_bugs(app: App):
    """Checks for any known bug conditions and recommends user action.
    This is a best-effort check
    """
    app.installer_step_count += 1
    ensure_sys_deps(app=app)
    app.installer_step += 1

    # Begin workaround #435
    # FIXME: #435 Remove this check when the issue is fixed upstream in wine    
    # Check to see if our default browser is chromium, google-chrome, brave, or vivaldi 
    # in that case prompt the user to switch to the wine beta channel
    #
    # This check is best-effort and may fail if the .desktop entry for chromium uses a naming convention
    # other than the one used on the debian package.

    chromium_detected: bool = False
    snap_or_flatpak_detected: bool = False

    try:
        result = system.run_command(
            "xdg-mime query default x-scheme-handler/https"
        )
        if result:
            command_output: str = result.stdout
            desktop_file_name = command_output.strip()
            command_output = desktop_file_name.lower()

            # Abbr. list from https://en.wikipedia.org/wiki/Chromium_(web_browser)#Browsers_based_on_Chromium
            # Known chromium based .desktops:
            # chromium_chromium.desktop - Debian Chromium (.deb and snap)
            # google-chrome and com.google.Chrome.desktop - Debian Google Chrome
            # brave-browser.desktop and com.brave.Browser.desktop - Debian Brave
            # vivaldi-stable.desktop - Debian Vivaldi
            # dooble.desktop - Debian Dooble
            # opera.desktop - Debian Opera
            # org.qutebrowser.qutebrowser.desktop - Debian Qutebrowser
            # org.kde.falkon.desktop - Debian Falkon
            if (
               "chromium" in command_output
               or "chrome" in command_output
               or "brave" in command_output
               or "vivaldi" in command_output
               or "dooble" in command_output
               or "falkon" in command_output
               or "qutebrowser" in command_output
               or "opera" in command_output
            ):
               chromium_detected = True
            
            # Now check the .desktop's Exec line for either "flatpak" or "/snap/bin" if either are found, fail as well.
            xdg_data_dirs = os.getenv("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
           
            found: bool = False

            for xdg_data_dir in xdg_data_dirs.split(":"):
                desktop_file_path = (Path(xdg_data_dir) / "applications" / desktop_file_name)
                if desktop_file_path.exists():
                    found = True
                    lines = desktop_file_path.read_text().splitlines()
                    lines = list(filter(lambda line: line.lower().startswith("exec="), lines))
                    if any("/snap/bin" in line or "flatpak" in line for line in lines):
                        snap_or_flatpak_detected = True
            
            if not found:
                logging.warning("Cannot find the desktop file in question")
    except subprocess.CalledProcessError as e:
        logging.warning(
            "Failed to check if chromium will be used - "
            "sign in button MAY NOT function if chromium is the default browser. "
            f"Error was as follows: {e}"
        )

    if chromium_detected or snap_or_flatpak_detected:
        if chromium_detected:
            logging.warning("Detected chromium based browser")
        elif snap_or_flatpak_detected:
            logging.warning("Detected snap or flatpak browser")
        if app.conf.wine_binary == constants.WINE_RECOMMENDED_SIGIL:
            logging.info("Switching user to the beta wine branch due to issue #435")
            app.conf.wine_binary = constants.WINE_BETA_SIGIL
        elif app.conf.wine_binary == constants.WINE_BETA_SIGIL:
            # No need to do anything
            pass
        else:
            logging.warning("Sign In button may not launch the browser due to issue #435")

    # End workaround #435


def ensure_appimage_download(app: App):
    app.installer_step_count += 1
    try:
        check_for_known_bugs(app=app)
    except Exception:
        logging.exception("Failed to check for known bugs - assuming everything is fine and continuing install.")
    app.installer_step += 1
    if (
        app.conf.faithlife_product_version != '9' 
        and not str(app.conf.wine_binary).lower().endswith('appimage')
        and app.conf.wine_binary not in [constants.WINE_BETA_SIGIL, constants.WINE_RECOMMENDED_SIGIL]
    ):
        return
    app.status("Ensuring wine AppImage is downloaded…")

    downloaded_file = None
    appimage_path = app.conf.wine_appimage_recommended_file_name 
    download_url = app.conf.wine_appimage_recommended_url

    if (
        app.conf.wine_binary == constants.WINE_BETA_SIGIL
        or (
            app.conf.wine_appimage_beta_file_name is not None 
            # It was set to this manually.
            and app.conf.wine_binary == f"{constants.RELATIVE_BINARY_DIR}/{app.conf.wine_appimage_beta_file_name}"
        )
    ):
        if (
            app.conf.wine_appimage_beta_file_name is not None
            and app.conf.wine_appimage_beta_url is not None
        ):
            appimage_path = app.conf.wine_appimage_beta_file_name
            download_url = app.conf.wine_appimage_beta_url
    elif (
        app.conf.wine_binary == constants.WINE_RECOMMENDED_SIGIL
        or (
            app.conf.wine_appimage_recommended_file_name is not None 
            # It was set to this manually.
            and app.conf.wine_binary ==
              f"{constants.RELATIVE_BINARY_DIR}/{app.conf.wine_appimage_recommended_file_name}"
        )
    ):
        appimage_path = app.conf.wine_appimage_recommended_file_name
        download_url = app.conf.wine_appimage_recommended_url
    else:
        logging.warning("Could not find which appimage to download, returning early.")
        return

    filename = Path(appimage_path).name
    downloaded_file = utils.get_downloaded_file_path(app.conf.download_dir, filename)
    if not downloaded_file:
        downloaded_file = f"{app.conf.download_dir}/{filename}"
    network.logos_reuse_download(
        download_url,
        filename,
        app.conf.download_dir,
        app=app,
    )
    logging.debug(f"> File exists?: {downloaded_file}: {Path(downloaded_file).is_file()}")
    
    app.conf.wine_binary = downloaded_file


def ensure_wine_executables(app: App):
    app.installer_step_count += 1
    ensure_appimage_download(app=app)
    app.installer_step += 1
    app.status("Ensuring wine executables are available…")

    create_wine_appimage_symlinks(app=app)

    # PATH is modified if wine appimage isn't found, but it's not modified
    # during a restarted installation, so shutil.which doesn't find the
    # executables in that case.
    logging.debug(f"> {app.conf.wine_binary=}")
    logging.debug(f"> {app.conf.wine64_binary=}")
    logging.debug(f"> {app.conf.wineserver_binary=}")


def ensure_winetricks_executable(app: App):
    app.installer_step_count += 1
    ensure_wine_executables(app=app)
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
    wine.set_renderer(app=app, wine64_binary=app.conf.wine64_binary, value='gdi')

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
    logging.debug('- ICU data files')

    wine.enforce_icu_data_files(app=app)

    logging.debug('> ICU data files installed')


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
    if constants.RUNMODE == 'binary':
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
        app.status(
            "Running from source. Skipping launcher copy."
        )


def ensure_launcher_shortcuts(app: App):
    app.installer_step_count += 1
    ensure_launcher_executable(app=app)
    app.installer_step += 1
    app.status("Creating launcher shortcuts…")
    if constants.RUNMODE == 'binary':
        app.status("Creating launcher shortcuts…")
        create_launcher_shortcuts(app)
    else:
        # This is done so devs can run this without it clobbering their install
        app.status(
            f"Runmode is '{constants.RUNMODE}'. Won't create desktop shortcuts",
        )

def install(app: App):
    """Entrypoint for installing"""
    app.status('Installing…')
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


def create_wine_appimage_symlinks(app: App):
    app.status("Creating wine appimage symlinks…")
    appdir_bindir = Path(app.conf.installer_binary_dir)
    os.environ['PATH'] = f"{app.conf.installer_binary_dir}:{os.getenv('PATH')}"
    # Ensure AppImage symlink.
    appimage_link = appdir_bindir / app.conf.wine_appimage_link_file_name
    if app.conf.wine_binary_code not in ['AppImage', 'Recommended'] or app.conf.wine_appimage_path is None: 
        logging.debug("No need to symlink non-appimages")
        return
    
    # Only use the appimage_path if it exists
    # It may not exist if it was an old install's .appimage
    # where the install dir has been cleared.
    if app.conf.wine_appimage_path.exists():
        appimage_filename = app.conf.wine_appimage_path.name
    else:
        appimage_filename = app.conf.wine_appimage_recommended_file_name
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

    # NOTE: if we symlink "winetricks" then the log is polluted with:
    # "Executing: cd /tmp/.mount_winet.../bin"
    (appdir_bindir / "winetricks").unlink(missing_ok=True)

    # Ensure wine executables symlinks.
    for name in ["wine", "wine64", "wineserver", "winetricks"]:
        p = appdir_bindir / name
        p.unlink(missing_ok=True)
        p.symlink_to(f"./{app.conf.wine_appimage_link_file_name}")


def create_desktop_file(
    filename: str,
    app_name: str,
    exec_cmd: str,
    generic_name: str | None = None,
    comment: str | None = None,
    icon_path: str | Path | None = None,
    wm_class: str | None = None,
    additional_keywords: list[str] | None = None,
    mime_types: list[str] | None = None,
    terminal: Optional[bool] = None
):
    contents = f"""[Desktop Entry]
Name={app_name}
Type=Application
Exec={exec_cmd}
Categories=Education;Spirituality;Languages;Literature;Maps;
Keywords=Logos;Verbum;FaithLife;Bible;Control;Christianity;Jesus;{";".join(additional_keywords or [])}
"""
    contents += f"Terminal={"true" if terminal is True else "false"}\n"
    if generic_name:
        contents += f"GenericName={generic_name}\n"
    if comment:
        contents += f"Comment={comment}\n"
    if icon_path:
        contents += f"Icon={icon_path}\n"
    if mime_types:
        contents += f"MimeType={";".join(mime_types)}\n"

    if wm_class:
        contents += f"StartupWMClass={wm_class}\n"
    else:
        contents += "StartupNotify=false\n"

    xdg_data_home = Path(constants.XDG_DATA_HOME)
    launcher_path = xdg_data_home / 'applications' / filename
    if launcher_path.is_file():
        logging.info(f"Removing desktop launcher at {launcher_path}.")
        launcher_path.unlink()
    # Ensure the parent directory exists
    launcher_path.parent.mkdir(parents=True, exist_ok=True)

    logging.info(f"Creating desktop launcher at {launcher_path}.")
    with launcher_path.open('w') as f:
        f.write(contents)
    os.chmod(launcher_path, 0o755)
    return launcher_path


def create_launcher_shortcuts(app: App):
    # Set variables for use in launcher files.
    flproduct = app.conf.faithlife_product
    installdir = Path(app.conf.install_dir)
    logos_icon_src = constants.APP_IMAGE_DIR / f"{flproduct}-128-icon.png"
    app_icon_src = constants.APP_IMAGE_DIR / 'icon.png'

    if not installdir.is_dir():
        app.exit("Can't create launchers because the installation folder does not exist.") 
    app_dir = Path(installdir) / 'data'
    logos_icon_path = app_dir / logos_icon_src.name
    app_icon_path = app_dir / app_icon_src.name

    if constants.RUNMODE == 'binary':
        oudedetai_executable = f"{installdir}/{constants.BINARY_NAME}"
    elif constants.RUNMODE == "source":
        script = Path(sys.argv[0]).expanduser().resolve()
        repo_dir = None
        for p in script.parents:
            for c in p.iterdir():
                if c.name == '.git':
                    repo_dir = p
                    break
        if repo_dir is None:
            app.exit("Could not find .git directory from arg 0")
        # Find python in virtual environment.
        py_bin = next(repo_dir.glob('*/bin/python'))
        if not py_bin.is_file():
            app.exit("Could not locate python binary in virtual environment.")
        oudedetai_executable = f"env DIALOG=tk {py_bin} {script}"
    elif constants.RUNMODE in ["snap", "flatpak"]:
        logging.info(f"Not creating launcher shortcuts, {constants.RUNMODE} already handles this") 
        return

    for (src, path) in [(app_icon_src, app_icon_path), (logos_icon_src, logos_icon_path)]:
        if not path.is_file():
            app_dir.mkdir(exist_ok=True)
            shutil.copy(src, path)
        else:
            logging.info(f"Icon found at {path}.")

    # Create Logos/Verbum desktop file.
    logos_path = create_desktop_file(
        filename=f"{flproduct}Bible.desktop",
        app_name=f"{flproduct}",
        generic_name="Bible",
        comment="Runs Faithlife Bible Software via Wine (snap). Community supported.",
        exec_cmd=f"{oudedetai_executable} --run-installed-app",
        icon_path=logos_icon_path,
        wm_class=f"{flproduct.lower()}.exe",
        additional_keywords=["Catholic"] if flproduct == "Verbum" else None
    )
    logging.debug(f"> File exists?: {logos_path}: {logos_path.is_file()}")
    # Create Ou Dedetai desktop file.
    app_path = create_desktop_file(
        filename=f"{constants.BINARY_NAME}.desktop",
        app_name=constants.APP_NAME,
        generic_name="FaithLife App Installer",
        comment="Installs and manages either Logos or Verbum via wine. Community supported.",
        exec_cmd=oudedetai_executable,
        icon_path=app_icon_path,
        wm_class=constants.BINARY_NAME,
    )
    logging.debug(f"> File exists?: {app_path}: {app_path.is_file()}")

    # Register URL scheme handlers:
    # logos4 - to facilitate Logos 40.1+ login OAuth flow
    # libronixdls - allows opening of bible links from the browser

    if not app.conf.logos_exe_windows_path:
        logging.error("Failed to register MIME types with system due to missing wine exe path")
        return

    url_handler_desktop_filename = f"{flproduct}-url-handler.desktop"
    # Create the desktop file to register the MIME types.
    app_path = create_desktop_file(
        filename=url_handler_desktop_filename,
        app_name=f"{flproduct} URL Handler",
        comment="Handles logos4: and libronixdls: URL Schemes",
        exec_cmd=f"{oudedetai_executable} --wine '{app.conf.logos_exe_windows_path.replace('\\','\\\\')}' '%u'",
        icon_path=app_icon_path,
        mime_types=["x-scheme-handler/logos4","x-scheme-handler/libronixdls"],
        terminal=True
    )
    # For most users Logos will be "installed" at this point, if we fail here there is no easy
    # way in the current flow to re-apply these - and this isn't required for Logos to function,
    # more of a nice to have. While it would be nice for support reasons not to branch here - 
    # which is more important: a passing exit code doing what we could to setup Logos, or 
    # everything that we do - even that which is optional such as this - passes?

    # On most systems these commands have the effect of adding the following to ~/.config/mimetypes:
    # ```
    # [Default Applications]
    # x-scheme-handler/logos4=logos4.desktop
    # x-scheme-handler/libronixdls=libronixdls.desktop
    # ```
    try:
        system.run_command([
            "xdg-mime",
            "default",
            url_handler_desktop_filename,
            "x-scheme-handler/logos4"
        ])
        system.run_command([
            "xdg-mime",
            "default",
            url_handler_desktop_filename,
            "x-scheme-handler/libronixdls"
        ])
    except subprocess.CalledProcessError:
        logging.exception("Failed to register MIME types with system")

    # Now best-effort update the desktop database
    if shutil.which("update-desktop-database") is not None:
        try:
            system.run_command(["update-desktop-database", f"{Path(constants.XDG_DATA_HOME) / 'applications'}"])
        except Exception as e:
            logging.warning(f"Failed to update the desktop databse (not strictly required on all systems): {e}")