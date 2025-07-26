from dataclasses import dataclass
import logging
import os
import shutil
import subprocess
from pathlib import Path
from packaging.version import Version
import tempfile
from typing import IO, Optional

from ou_dedetai import constants
from ou_dedetai.app import App

from . import network
from . import system
from . import utils

def check_wineserver(app: App) -> bool:
    # FIXME: if the wine version changes, we may need to restart the wineserver
    # (or at least kill it). Gotten into several states in dev where this happend
    # Normally when an msi install failed
    try:
        process = run_wine_during_install(app, app.conf.wineserver_binary)
        if not process:
            logging.debug("Failed to spawn wineserver to check it")
            return False
        # We already check the return code in run_wine_during_install.
        # If there is a non-zero exit code subprocess.CalledProcessError will be raised
        return True
    except subprocess.CalledProcessError:
        return False


def wineserver_kill(app: App):
    if check_wineserver(app):
        process = run_wine_during_install(
            app,
            app.conf.wineserver_binary,
            exe_args=["-k"]
        )
        if not process:
            logging.debug("Failed to spawn wineserver to kill it")
            return False


def wineserver_wait(app: App):
    if check_wineserver(app):
        process = run_wine_during_install(
            app,
            app.conf.wineserver_binary,
            exe_args=["-w"]
        )
        if not process:
            logging.debug("Failed to spawn wineserver to wait for it")
            return False


@dataclass
class WineRelease:
    major: int
    minor: int
    release: Optional[str]


def get_devel_or_stable(version: str) -> str:
    # Wine versioning states that x.0 is always stable branch, while x.y is devel.
    # Ref: https://gitlab.winehq.org/wine/wine/-/wikis/Wine-User's-Guide#wine-from-winehq
    if version.split('.')[1].startswith('0'):
        return 'stable'
    else:
        return 'devel'


# FIXME: consider raising exceptions on error
def get_wine_release(binary: str) -> tuple[Optional[WineRelease], str]:
    cmd = [binary, "--version"]
    try:
        version_string = subprocess.check_output(cmd, encoding='utf-8').strip()
        logging.debug(f"Version string: {str(version_string)}")
        branch: Optional[str]
        try:
            wine_version, branch = version_string.split()  # release = (Staging)
            branch = branch.lstrip('(').rstrip(')').lower()  # remove parens
        except ValueError:
            # Neither "Devel" nor "Stable" release is noted in version output
            wine_version = version_string
            branch = get_devel_or_stable(wine_version)
        version = wine_version.lstrip('wine-')
        logging.debug(f"Wine branch of {binary}: {branch}")

        ver_major = int(version.split('.')[0].lstrip('wine-'))  # remove 'wine-'
        ver_minor_str = version.split('.')[1]
        # In the case the version is an rc like wine-10.0-rc5
        if '-' in ver_minor_str:
            ver_minor_str = ver_minor_str.split("-")[0]
        ver_minor = int(ver_minor_str)

        wine_release = WineRelease(ver_major, ver_minor, branch)
        logging.debug(f"Wine release of {binary}: {str(wine_release)}")
        if ver_major == 0:
            return None, "Couldn't determine wine version."
        else:
            return wine_release, "yes"

    except subprocess.CalledProcessError as e:
        return None, f"Error running command: {e}"

    except ValueError as e:
        return None, f"Error parsing version: {e}"

    except Exception as e:
        return None, f"Error: {e}"


@dataclass
class WineRule:
    major: int
    proton: bool
    minor_bad: list[int]
    allowed_releases: list[str]
    devel_allowed: Optional[int] = None


def check_wine_rules(
    wine_release: Optional[WineRelease],
    release_version: Optional[str],
    faithlife_product_version: str
):
    # Does not check for Staging. Will not implement: expecting merging of
    # commits in time.
    logging.debug(f"Checking {wine_release} for {release_version}.")
    if faithlife_product_version == "10":
        if release_version is not None and Version(release_version) < Version("30.0.0.0"): 
            required_wine_minimum = [7, 18]
        else:
            required_wine_minimum = [9, 10]
    elif faithlife_product_version == "9":
        required_wine_minimum = [7, 0]
    else:
        raise ValueError(
            "Invalid target version, expecting 9 or 10 but got: "
            f"{faithlife_product_version} ({type(faithlife_product_version)})"
        )

    rules: list[WineRule] = [
        # Proton release tend to use the x.0 release, but can include changes found in devel/staging
        # exceptions to minimum
        WineRule(major=7, proton=True, minor_bad=[], allowed_releases=["staging"]),
        # devel permissible at this point
        WineRule(major=8, proton=False, minor_bad=[0], allowed_releases=["staging"], devel_allowed=16), 
        WineRule(major=9, proton=False, minor_bad=[], allowed_releases=["devel", "staging"]),  
        WineRule(major=10, proton=False, minor_bad=[], allowed_releases=["stable", "devel", "staging"]) 
    ]

    major_min, minor_min = required_wine_minimum
    if wine_release:
        major = wine_release.major
        minor = wine_release.minor
        release_type = wine_release.release
        result = True, "None"  # Whether the release is allowed; error message
        for rule in rules:
            if major == rule.major:
                # Verify release is allowed
                if release_type not in rule.allowed_releases:
                    if minor >= (rule.devel_allowed or float('inf')):
                        if release_type not in ["staging", "devel"]:
                            result = (
                                False,
                                (
                                    f"Wine release needs to be devel or staging. "
                                    f"Current release: {release_type}."
                                )
                            )
                            break
                    else:
                        result = (
                            False,
                            (
                                f"Wine release needs to be {rule.allowed_releases}. "
                                f"Current release: {release_type}."
                            )
                        )
                        break
                # Verify version is allowed
                if minor in rule.minor_bad:
                    result = False, f"Wine version {major}.{minor} will not work."
                    break
                if major < major_min:
                    result = (
                        False,
                        (
                            f"Wine version {major}.{minor} is "
                            f"below minimum required ({major_min}.{minor_min}).")
                    )
                    break
                elif major == major_min and minor < minor_min:
                    if not rule.proton:
                        result = (
                            False,
                            (
                                f"Wine version {major}.{minor} is "
                                f"below minimum required ({major_min}.{minor_min}).")
                        )
                        break
        logging.debug(f"Result: {result}")
        return result
    else:
        return True, "Default to trusting user override"


def check_wine_version_and_branch(release_version: Optional[str], test_binary,
                                  faithlife_product_version):
    if not os.path.exists(test_binary):
        reason = "Binary does not exist."
        return False, reason

    if not os.access(test_binary, os.X_OK):
        reason = "Binary is not executable."
        return False, reason

    wine_release, error_message = get_wine_release(test_binary)

    if wine_release is None:
        return False, error_message

    result, message = check_wine_rules(
        wine_release,
        release_version,
        faithlife_product_version
    )
    if not result:
        return result, message

    if wine_release.major > 9:
        pass

    return True, "None"


def initializeWineBottle(wine64_binary: str, app: App):
    app.status("Initializing wine bottle…")
    logging.debug(f"{wine64_binary=}")
    # Avoid wine-mono window
    wine_dll_override="mscoree="
    logging.debug(f"Running: {wine64_binary} wineboot --init")
    run_wine_during_install(
        app=app,
        wine_binary=wine64_binary,
        exe='wineboot',
        exe_args=['--init'],
        init=True,
        additional_wine_dll_overrides=wine_dll_override
    )


def set_win_version(app: App, exe: str, windows_version: str):
    if exe == "logos":
        # This operation is equivilent to f"winetricks -q settings {windows_version}"
        # but faster
        run_wine_during_install(
            app,
            app.conf.wine_binary,
            exe_args=('winecfg', '/v', windows_version)
        )

    elif exe == "indexer":
        reg = f"HKCU\\Software\\Wine\\AppDefaults\\{app.conf.faithlife_product}Indexer.exe"
        exe_args = [
            'add',
            reg,
            "/v", "Version",
            "/t", "REG_SZ",
            "/d", f"{windows_version}", "/f",
            ]
        process = run_wine_during_install(
            app,
            app.conf.wine_binary,
            exe='reg',
            exe_args=exe_args
        )
        if process is None:
            app.exit("Failed to spawn command to set windows version for indexer")


def wine_reg_query(app: App, key_name: str, value_name: str) -> Optional[str]:
    """Query the registry

    Example command and output:

    ```    
    $ wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts" /v "Arial (TrueType)"

    HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts
        Arial (TrueType)    REG_SZ    Z:\\usr\\share\\fonts\\truetype\\msttcorefonts\\Arial.ttf

    ```
    """
    process = run_wine_completed_process(
        app=app,
        wine_binary=app.conf.wine64_binary,
        exe="reg.exe",
        exe_args=[
            "query",
            key_name,
            "/v",
            value_name
        ]
    )
    if process.returncode == 1:
        # Key not found
        return None
    elif process.returncode == 0:
        # Parse output?
        for line in process.stdout.rstrip().splitlines():
            # If line is empty that's not what we're looking for
            if not line:
                continue
            if line.strip() == key_name:
                continue
            if line.lstrip().startswith(value_name) and "REG_SZ" in line:
                # This is the line in question
                return line.split(value_name)[1].split("REG_SZ")[1].strip()
        logging.warning(f"Failed to parse the registry query: {process.stdout.rstrip()}") 
        return None
    else:
        # Unknown exit code
        failed = f"Failed to query the registry: Unknown Exit code {process.returncode}"
        logging.debug(f"{failed}. {process=}")
        app.exit(f"{failed}: {key_name} {value_name}")


def wine_reg_install(app: App, name: str, reg_text: str, wine64_binary: str):
    with tempfile.TemporaryDirectory() as tempdir:
        reg_file = Path(tempdir) / name
        reg_file.write_text(reg_text)
        app.status(f"Installing registry file: {reg_file}")  
        try:
            process = run_wine_during_install(
                app=app,
                wine_binary=wine64_binary,
                exe="regedit.exe",
                exe_args=[str(reg_file)]
            )
            if process is None:
                app.exit("Failed to spawn command to install reg file")
            logging.info(f"{reg_file} installed.")
            wineserver_wait(app)
        except subprocess.CalledProcessError:
            failed = "Failed to install reg file"
            logging.exception(f"{failed}")
            app.exit(f"{failed}: {reg_file}")
        finally:
            reg_file.unlink()


def disable_winemenubuilder(app: App, wine64_binary: str):
    name='disable-winemenubuilder.reg'
    reg_text = r'''REGEDIT4

[HKEY_CURRENT_USER\Software\Wine\DllOverrides]
"winemenubuilder.exe"=""
'''
    wine_reg_install(app, name, reg_text, wine64_binary)


def set_renderer(app: App, wine64_binary: str, value: str):
    name=f'set-renderer-to-{value}.reg'
    reg_text = rf'''REGEDIT4

[HKEY_CURRENT_USER\Software\Wine\Direct3D]
"renderer"="{value}"
'''
    wine_reg_install(app, name, reg_text, wine64_binary)


def set_fontsmoothing_to_rgb(app: App, wine64_binary: str):
    # Possible registry values:
    # "disable":      FontSmoothing=0; FontSmoothingOrientation=1; FontSmoothingType=0
    # "gray/grey":    FontSmoothing=2; FontSmoothingOrientation=1; FontSmoothingType=1
    # "bgr":          FontSmoothing=2; FontSmoothingOrientation=0; FontSmoothingType=2
    # "rgb":          FontSmoothing=2; FontSmoothingOrientation=1; FontSmoothingType=2
    # https://github.com/Winetricks/winetricks/blob/8cf82b3c08567fff6d3fb440cbbf61ac5cc9f9aa/src/winetricks#L17411

    name='set-fontsmoothing-to-rgb.reg'
    reg_text = r'''REGEDIT4

[HKEY_CURRENT_USER\Control Panel\Desktop]
"FontSmoothing"="2"
"FontSmoothingGamma"=dword:00000578
"FontSmoothingOrientation"=dword:00000001
"FontSmoothingType"=dword:00000002
'''
    wine_reg_install(app, name, reg_text, wine64_binary)


def install_msi(app: App):
    app.status(f"Running MSI installer: {app.conf.faithlife_installer_name}.")
    # Define the Wine executable and initial arguments for msiexec
    wine_binary = app.conf.wine64_binary
    exe_args = ["/i", f"{app.conf.install_dir}/data/{app.conf.faithlife_installer_name}"]

    # Add passive mode if specified
    if app.conf._overrides.faithlife_install_passive is True:
        # Ensure the user agrees to the EULA. Exit if they don't.
        if (
            app.conf._overrides.agreed_to_faithlife_terms or
            app.approve_or_exit("Do you agree to Faithlife's EULA? https://faithlife.com/terms")
        ):
            exe_args.append("/passive")

    # Add MST transform if needed
    release_version = app.conf.installed_faithlife_product_release or app.conf.faithlife_product_release
    if release_version is not None and Version(release_version) > Version("39.0.0.0"): 
        # Define MST path and transform to windows path.
        mst_path = constants.APP_ASSETS_DIR / "LogosStubFailOK.mst"
        transform_winpath = run_wine_completed_process(
            app=app,
            wine_binary=wine_binary,
            exe_args=['winepath', '-w', mst_path]
        ).stdout.rstrip()
        exe_args.append(f'TRANSFORMS={transform_winpath}')
        logging.debug(f"TRANSFORMS windows path added: {transform_winpath}")

    # Log the msiexec command and run the process
    logging.info(f"Running: {wine_binary} msiexec {' '.join(exe_args)}")
    result = run_wine_during_install(app, wine_binary, exe="msiexec", exe_args=exe_args)
    if result is not None:
        # Wait in order to get the exit status.
        result.wait()
    if result is None or result.returncode != 0:
        app.exit("Logos Installer failed.") 
    return result


def run_winetricks(app: App, *args):
    cmd = [*args]
    if "-q" not in args and app.conf.winetricks_binary:
        cmd.insert(0, "-q")
    logging.info(f"running \"winetricks {' '.join(cmd)}\"")
    try:
        process = run_wine_during_install(app, app.conf.winetricks_binary, exe_args=cmd)
        if process is None:
            app.exit("Failed to spawn winetricks")
    except subprocess.CalledProcessError:
        logging.exception(f"\"winetricks {' '.join(cmd)}\" Failed!")
        app.exit(f"\"winetricks {' '.join(cmd)}\" Failed!")
    logging.info(f"\"winetricks {' '.join(cmd)}\" DONE!")
    logging.debug(f"procs using {app.conf.wine_prefix}:")
    for proc in utils.get_procs_using_file(app.conf.wine_prefix):
        logging.debug(f"winetricks proc: {proc=}")
    else:
        logging.debug('winetricks proc: <None>')


def install_fonts(app: App):
    """Installs all required fonts:
    
    - arial
    """
    fonts_dir = Path(app.conf.wine_prefix) / "drive_c" / "windows" / "Fonts"
    fonts = ["arial"]
    for i, f in enumerate(fonts):
        registry_key = wine_reg_query(
            app,
            "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts", 
            f"{f.capitalize()} (TrueType)"
        )
        if registry_key is not None and registry_key != f"{f}.ttf":
            # Can hit this case with the debian package ttf-mscorefonts-installer
            logging.debug(f"Found font {f} already installed by other means, no need to install.") 
            continue
        # This case doesn't happen normally, but still good to check.
        # Now we need to check to see if there is a registry key saying it's in Fonts
        # but in reality it's not.
        if registry_key == f"{f}.ttf" and (fonts_dir / f"{f}.ttf").exists():
            logging.debug(f"Found font {f} already in fonts dir, no need to install.")
            continue
        # Font isn't installed, continue to install with winetricks.
        app.status(f"Configuring font: {f}…", i / len(fonts))
        args = [f]
        run_winetricks(app, *args)


def get_winecmd_encoding(app: App) -> Optional[str]:
    # Get wine system's cmd.exe encoding for proper decoding to UTF8 later.
    logging.debug("Getting wine system's cmd.exe encoding.")
    registry_value = get_registry_value(
        'HKCU\\Software\\Wine\\Fonts',
        'Codepages',
        app
    )
    if registry_value is not None:
        codepages: str = registry_value.split(',')
        return codepages[-1]
    else:
        m = "wine.wine_proc: wine.get_registry_value returned None."
        logging.error(m)
        return None


def run_wine_completed_process(
    app: App,
    wine_binary: str,
    exe=None,
    exe_args=None,
    additional_wine_dll_overrides: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    """Like run_wine_proc but outputs a CompletedProcess
    and sets it's output to text

    Useful when wanting to parse the output for wine commands
    """
    env = get_wine_env(app, additional_wine_dll_overrides)
    command = [wine_binary]
    if exe is not None:
        command.append(exe)
    if exe_args:
        command.extend(exe_args)
    return subprocess.run(
        command,
        env=system.fix_ld_library_path(env),
        capture_output=True,
        text=True,
    )


def run_wine_process(
    app: App,
    wine_binary: str | Path,
    stdout: IO[str],
    stderr: IO[str],
    stdin = None,
    exe=None,
    exe_args=None,
    additional_wine_dll_overrides: Optional[str] = None,
) -> Optional[subprocess.Popen[bytes]]:
    """Runs wine directly
    
    Args:
    - app: App
    - stdout: Where to send stdout, must be a file descriptor
    - stderr: Where to send stderr, must be a file descriptor
    - stderr: Where stdin should come from, must be a file descriptor
    - exe: The windows executable to run
    - exe_args: arguments to the aforementioned exe
    - init: whether or not this call is to initialize the bottle
    - additional_wine_dll_overrides: Add to WINEDLLOVERRIDES
    """
    env = get_wine_env(app, additional_wine_dll_overrides)
    if isinstance(wine_binary, Path):
        wine_binary = str(wine_binary)

    command = [wine_binary]
    if exe is not None:
        command.append(exe)
    if exe_args:
        command.extend(exe_args)

    cmd = f"Running wine cmd: '{' '.join(command)}'"
    logging.debug(cmd)
    try:
        stdout.write(f"{utils.get_timestamp()}: {cmd}\n")
        # FIXME: consider calling Popen directly here so we can remove the
        # run_wine_proc_completed_process function - as it is nearly a duplicate
        # of this one, but with a different arg to Popen.
        return system.popen_command(
            command,
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            env=env,
            start_new_session=True,
            encoding='utf-8'
        )

    except subprocess.CalledProcessError as e:
        logging.error(f"Exception running '{' '.join(command)}': {e}")
    return None


def run_wine_application(
    app: App,
    wine_binary: str | Path,
    exe=None,
    exe_args=None,
    additional_wine_dll_overrides: Optional[str] = None,
) -> Optional[subprocess.Popen[bytes]]:
    """Run a wine application.
     
    Store the log in a dedicated file, keeping the previous log.
    """
    current_log_path = Path(app.conf.app_wine_log_path)
    previous_log_path = Path(app.conf.app_wine_log_previous_path)
    if current_log_path.exists():
        shutil.move(current_log_path, previous_log_path)
    with open(current_log_path, 'w') as wine_log:
        return run_wine_process(
            app=app,
            wine_binary=wine_binary,
            stdout=wine_log,
            stderr=wine_log,
            exe=exe,
            exe_args=exe_args,
            additional_wine_dll_overrides=additional_wine_dll_overrides
        )


def run_wine_during_install(
    app: App,
    wine_binary: str | Path,
    exe=None,
    exe_args=list(),
    init=False,
    additional_wine_dll_overrides: Optional[str] = None,
) -> Optional[subprocess.Popen[bytes]]:
    """Runs a wine process as part of the install process.
    Waits for wine to complete before returning.
    Checks exit code to ensure it is 0
    
    Logs are dumped in the python logger (subject to their rotation).
    This function also waits on the process to finish.
    
    Raises:
    - subprocess.CalledProcessError if returncode != 0
    """
    with tempfile.NamedTemporaryFile(mode="w+") as temp_file:
        process = run_wine_process(
            app=app,
            wine_binary=wine_binary,
            stdout=temp_file,
            stderr=temp_file,
            exe=exe,
            exe_args=exe_args,
            additional_wine_dll_overrides=additional_wine_dll_overrides
        )
        if process:
            if exe:
                full_command_string = f"{wine_binary} {exe} {" ".join(exe_args)}"
            else:
                full_command_string = f"{wine_binary} {" ".join(exe_args)}"
            logging.debug(f"Waiting on: {full_command_string}")
            process.wait()
            logging.debug(f"Wine process {full_command_string} "
                          f"completed with: {process.returncode}. "
                          "Dumping log:")
            # Now read from the tempfile and echo into our application log.
            with open(temp_file.name, "r") as temp_log_file:
                while line := temp_log_file.readline():
                    logging.debug(f"> {line.rstrip()}")
            logging.debug(f"Finished dumping log {full_command_string}")
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode,
                    cmd=full_command_string,
                )
    return process


# FIXME: Consider when to re-run this if it changes.
# Perhaps we should have a "apply installation updates"
# or similar mechanism to ensure all of our latest methods are installed
# including but not limited to: system packages, icu files, fonts, registry
# edits, etc.
#
# Seems like we want to have a more holistic mechanism for ensuring
# all users use the latest and greatest.
# Sort of like an update, but for wine and all of the bits underneath "Logos" itself
def enforce_icu_data_files(app: App):
    app.status("Downloading ICU files…")
    icu_url = app.conf.icu_latest_version_url
    icu_latest_version = app.conf.icu_latest_version

    icu_filename = os.path.basename(icu_url).removesuffix(".tar.gz")
    # Append the version to the file name so it doesn't collide with previous versions
    icu_filename = f"{icu_filename}-{icu_latest_version}.tar.gz"
    network.logos_reuse_download(
        icu_url,
        icu_filename,
        app.conf.download_dir,
        app=app
    )

    app.status("Copying ICU files…")

    drive_c = f"{app.conf.wine_prefix}/drive_c"
    utils.untar_file(f"{app.conf.download_dir}/{icu_filename}", drive_c)

    # Ensure the target directory exists
    icu_win_dir = f"{drive_c}/icu-win/windows"
    if not os.path.exists(icu_win_dir):
        os.makedirs(icu_win_dir)

    shutil.copytree(icu_win_dir, f"{drive_c}/windows", dirs_exist_ok=True)
    app.status("ICU files copied.", 100)



def get_registry_value(reg_path, name, app: App):
    logging.debug(f"Get value for: {reg_path=}; {name=}")
    # FIXME: consider breaking run_wine_proc into a helper function before decoding is attempted
    # NOTE: Can't use run_wine_proc here because of infinite recursion while
    # trying to determine wine_output_encoding.
    value = None
    env = get_wine_env(app)

    cmd = [
        app.conf.wine64_binary,
        'reg', 'query', reg_path, '/v', name,
    ]
    err_msg = f"Failed to get registry value: {reg_path}\\{name}"
    encoding = app.conf._wine_output_encoding
    if encoding is None:
        encoding = 'UTF-8'
    try:
        result = system.run_command(
            cmd,
            encoding=encoding,
            env=env
        )
    except subprocess.CalledProcessError as e:
        if 'non-zero exit status' in str(e):
            logging.warning(err_msg)
            return None
    if result is not None and result.stdout is not None:
        for line in result.stdout.splitlines():
            if line.strip().startswith(name):
                value = line.split()[-1].strip()
                logging.debug(f"Registry value: {value}")
                break
    else:
        logging.critical(err_msg)
    return value


def get_wine_env(app: App, additional_wine_dll_overrides: Optional[str]=None) -> dict[str, str]: 
    logging.debug("Getting wine environment.")
    wine_env = os.environ.copy()
    winepath = Path(app.conf.wine_binary)
    if winepath.name != 'wine64':  # AppImage
        winepath = Path(app.conf.wine64_binary)
    wine_env_defaults = {
        'WINE': str(winepath),
        'WINEDEBUG': app.conf.wine_debug,
        'WINEDLLOVERRIDES': app.conf.wine_dll_overrides,
        'WINELOADER': str(winepath),
        'WINEPREFIX': app.conf.wine_prefix,
        'WINESERVER': app.conf.wineserver_binary,
    }
    for k, v in wine_env_defaults.items():
        wine_env[k] = v

    if additional_wine_dll_overrides is not None:
        wine_env["WINEDLLOVERRIDES"] += ";" + additional_wine_dll_overrides

    updated_env = {k: wine_env.get(k) for k in wine_env_defaults.keys()}

    # Needed for the wrapper script
    if app.conf.is_wine_binary_in_wine_rootfs:
        wine_env["LD_PRELOAD"] = f"libapprun_hooks.so:{wine_env.get("LD_PRELOAD","")}"
        wine_env["PATH"] = f"{app.conf.wine_rootfs}:{wine_env.get("PATH", "")}"
        wine_env["LD_LIBRARY_PATH"] = f"{Path(app.conf.wine_rootfs) / "lib" / "x86_64-linux-gnu"}:{Path(app.conf.wine_rootfs) / "usr" / "lib" / "x86_64-linux-gnu"}:{wine_env.get("LD_LIBRARY_PATH", "")}"

    logging.debug(f"Wine env: {updated_env}")
    # Extra safe calling this here, it should be called run run_command anyways
    return system.fix_ld_library_path(wine_env)
