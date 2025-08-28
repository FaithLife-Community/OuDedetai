from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from collections.abc import MutableMapping
import zipfile
import distro
import logging
import os
import psutil
import platform
import shutil
import struct
import subprocess
import sys
import time

from ou_dedetai import constants, network
from ou_dedetai.app import App


def fix_ld_library_path(env: Optional[MutableMapping[str, str]]) -> dict[str, str]: 
    """Removes pyinstaller bundled dynamic linked libraries when executing commands

    - https://pyinstaller.org/en/latest/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application
    - https://pyinstaller.org/en/latest/runtime-information.html#library-path-considerations
    """
    # even when we don't pass env to Popen (or similar), we still don't want to use
    # pyinstaller's dynamic linked libraries.
    # In order to avoid this, we need to set env
    if env is None:
        env = dict(os.environ)
    else:
        env = dict(env)

    # Only do this when running in binary mode
    # Since LD_LIBRARY_PATH is core to how binaries work, we don't want it
    # modified unless we know we need to.
    if constants.RUNMODE == 'binary':
        # *BSD uses LD_LIBRARY_PATH, AIX uses LIBPATH
        for lp_key in ["LD_LIBRARY_PATH", "LIBPATH"]:
            lp_orig = env.pop(lp_key + '_ORIG', None)
            if lp_orig is not None:
                env[lp_key] = lp_orig  # restore the original, unmodified value
            else:
                # This happens when LD_LIBRARY_PATH was not set.
                # Remove the env var as a last resort:
                env.pop(lp_key, None)

    return env


def run_command(command, retries=1, delay=0, **kwargs) -> Optional[subprocess.CompletedProcess]:
    check = kwargs.get("check", True)
    text = kwargs.get("text", True)
    capture_output = kwargs.get("capture_output", True)
    shell = kwargs.get("shell", False)
    env = kwargs.get("env", None)
    cwd = kwargs.get("cwd", None)
    encoding = kwargs.get("encoding", None)
    cmdinput = kwargs.get("input", None)
    stdin = kwargs.get("stdin", None)
    stdout = kwargs.get("stdout", None)
    stderr = kwargs.get("stderr", None)
    timeout = kwargs.get("timeout", None)
    bufsize = kwargs.get("bufsize", -1)
    executable = kwargs.get("executable", None)
    pass_fds = kwargs.get("pass_fds", ())
    errors = kwargs.get("errors", None)
    preexec_fn = kwargs.get("preexec_fn", None)
    close_fds = kwargs.get("close_fds", True)
    universal_newlines = kwargs.get("universal_newlines", None)
    startupinfo = kwargs.get("startupinfo", None)
    creationflags = kwargs.get("creationflags", 0)
    restore_signals = kwargs.get("restore_signals", True)
    start_new_session = kwargs.get("start_new_session", False)
    user = kwargs.get("user", None)
    group = kwargs.get("group", None)
    extra_groups = kwargs.get("extra_groups", None)
    umask = kwargs.get("umask", -1)
    pipesize = kwargs.get("pipesize", -1)
    process_group = kwargs.get("process_group", None)

    if retries < 1:
        retries = 1

    if isinstance(command, str) and not shell:
        command = command.split()

    env = fix_ld_library_path(env)

    for attempt in range(retries):
        try:
            result: subprocess.CompletedProcess = subprocess.run(
                command,
                check=check,
                text=text,
                shell=shell,
                capture_output=capture_output,
                input=cmdinput,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                encoding=encoding,
                cwd=cwd,
                env=env,
                timeout=timeout,
                bufsize=bufsize,
                executable=executable,
                errors=errors,
                pass_fds=pass_fds,
                preexec_fn=preexec_fn,
                close_fds=close_fds,
                universal_newlines=universal_newlines,
                startupinfo=startupinfo,
                creationflags=creationflags,
                restore_signals=restore_signals,
                start_new_session=start_new_session,
                user=user,
                group=group,
                extra_groups=extra_groups,
                umask=umask,
                pipesize=pipesize,
                process_group=process_group
            )
            return result
        except subprocess.CalledProcessError as e:
            logging.error(f"Error occurred in run_command() while executing \"{command}\": {e}.")
            logging.debug(f"Command failed with output:\n{e.stdout}\nand stderr:\n{e.stderr}") 
            # FIXME: Move this logic to the caller
            if "lock" in str(e):
                logging.debug(f"Database appears to be locked. Retrying in {delay} seconds…")
                time.sleep(delay)
            else:
                raise e
        except Exception as e:
            logging.error(f"An unexpected error occurred when running {command}: {e}")
            return None

    logging.error(f"Failed to execute after {retries} attempts: '{command}'")
    return None


# FIXME: #300 refactor this to either return Popen or raise. No None.
def popen_command(command, retries=1, delay=0, **kwargs) -> Optional[subprocess.Popen[bytes]]:
    shell = kwargs.get("shell", False)
    env = kwargs.get("env", None)
    cwd = kwargs.get("cwd", None)
    stdin = kwargs.get("stdin", None)
    stdout = kwargs.get("stdout", None)
    stderr = kwargs.get("stderr", None)
    bufsize = kwargs.get("bufsize", -1)
    executable = kwargs.get("executable", None)
    pass_fds = kwargs.get("pass_fds", ())
    preexec_fn = kwargs.get("preexec_fn", None)
    close_fds = kwargs.get("close_fds", True)
    universal_newlines = kwargs.get("universal_newlines", None)
    startupinfo = kwargs.get("startupinfo", None)
    creationflags = kwargs.get("creationflags", 0)
    restore_signals = kwargs.get("restore_signals", True)
    start_new_session = kwargs.get("start_new_session", False)
    user = kwargs.get("user", None)
    group = kwargs.get("group", None)
    extra_groups = kwargs.get("extra_groups", None)
    umask = kwargs.get("umask", -1)
    pipesize = kwargs.get("pipesize", -1)
    process_group = kwargs.get("process_group", None)
    encoding = kwargs.get("encoding", None)
    errors = kwargs.get("errors", None)

    if retries < 1:
        retries = 1

    if isinstance(command, str) and not shell:
        command = command.split()

    env = fix_ld_library_path(env)

    for _ in range(retries):
        try:
            process = subprocess.Popen(
                command,
                shell=shell,
                env=env,
                cwd=cwd,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                bufsize=bufsize,
                executable=executable,
                pass_fds=pass_fds,
                preexec_fn=preexec_fn,
                close_fds=close_fds,
                universal_newlines=universal_newlines,
                startupinfo=startupinfo,
                creationflags=creationflags,
                restore_signals=restore_signals,
                start_new_session=start_new_session,
                user=user,
                group=group,
                extra_groups=extra_groups,
                umask=umask,
                pipesize=pipesize,
                process_group=process_group,
                encoding=encoding,
                errors=errors,
                text=False
            )
            return process

        except subprocess.CalledProcessError as e:
            logging.error(f"Error occurred in popen_command() while executing \"{command}\": {e}")
            # FIXME: Move this logic to the caller
            if "lock" in str(e):
                logging.debug(f"Database appears to be locked. Retrying in {delay} seconds…")
                time.sleep(delay)
            else:
                raise e
        except Exception as e:
            logging.error(f"An unexpected error occurred when running {command}: {e}")
            return None

    logging.error(f"Failed to execute after {retries} attempts: '{command}'")
    return None


def get_pids(query) -> list[psutil.Process]:
    results = []
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if process.info['cmdline'] is not None and query in process.info['cmdline']:
                results.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return results


def reboot(superuser_command: str):
    logging.info("Rebooting system.")
    command = f"{superuser_command} reboot now"
    run_command(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        capture_output=False,
        shell=True,
        text=True
    )
    sys.exit(0)


def get_dialog() -> str:
    """Returns which frontend the user prefers
    
    Uses "DIALOG" from environment if found,
    otherwise opens curses if the user has a tty
    
    Returns:
        dialog - tk (graphical), curses (terminal ui), or cli (command line)
    """
    if not os.environ.get('DISPLAY'):
        logging.critical("The installer does not work unless you are running a display")

    dialog = os.getenv('DIALOG')
    # find dialog
    if dialog is not None:
        dialog = dialog.lower()
        if dialog not in ['cli', 'curses', 'tk']:
            print("Valid values for DIALOG are 'cli', 'curses' or 'tk'.", file=sys.stderr)
            sys.exit(1)
        return dialog
    elif sys.__stdin__ is not None and sys.__stdin__.isatty():
        return 'curses'
    else:
        return 'tk'


def get_architecture() -> Tuple[str, int]:
    """Queries the device and returns which cpu architure and bits is supported
    
    Returns:
        architecture: x86_64 x86_32 or """
    machine = platform.machine().lower()
    bits = struct.calcsize("P") * 8

    # FIXME: consider conforming to a standard for the architecture name
    # normally see arm64 in lowercase for example and risc as riscv64 on
    # debian's support architectures for example https://wiki.debian.org/SupportedArchitectures
    if "x86_64" in machine or "amd64" in machine:
        architecture = "x86_64"
    elif "i386" in machine or "i686" in machine:
        architecture = "x86_32"
    elif "arm" in machine or "aarch64" in machine:
        if bits == 64:
            architecture = "ARM64"
        else:
            architecture = "ARM32"
    elif "riscv" in machine or "riscv64" in machine:
        if bits == 64:
            architecture = "RISC-V 64"
        else:
            architecture = "RISC-V 32"
    else:
        architecture = "Unknown"

    return architecture, bits


def install_elf_interpreter():
    # TODO: This probably needs to be changed to another install step that requests the 
    # user to choose a specific ELF interpreter between box64, FEX-EMU, and hangover.
    # That or else we have to pursue a particular interpreter
    # for the install routine, depending on what's needed
    logging.critical("ELF interpretation is not yet coded in the installer.")
    # architecture, bits = get_architecture()
    # if "x86_64" not in architecture:
    #     if config.ELFPACKAGES is not None:
    #         utils.install_packages(config.ELFPACKAGES)
    #     else:
    #         logging.critical(f"ELFPACKAGES is not set.")
    #         sys.exit(1)
    # else:
    #     logging.critical(f"ELF interpreter is not needed.")


def check_architecture():
    architecture, bits = get_architecture()
    logging.debug(f"Current Architecture: {architecture}, {bits}bit.")
    if "x86_64" in architecture:
        pass
    elif "ARM64" in architecture:
        logging.critical("Unsupported architecture. Requires box64 or FEX-EMU or Wine Hangover to be integrated.") 
        install_elf_interpreter()
    elif "RISC-V 64" in architecture:
        logging.critical("Unsupported architecture. Requires box64 or FEX-EMU or Wine Hangover to be integrated.") 
        install_elf_interpreter()
    elif "x86_32" in architecture:
        logging.critical("Unsupported architecture. Requires box64 or FEX-EMU or Wine Hangover to be integrated.") 
        install_elf_interpreter()
    elif "ARM32" in architecture:
        logging.critical("Unsupported architecture. Requires box64 or FEX-EMU or Wine Hangover to be integrated.") 
        install_elf_interpreter()
    elif "RISC-V 32" in architecture:
        logging.critical("Unsupported architecture. Requires box64 or FEX-EMU or Wine Hangover to be integrated.") 
        install_elf_interpreter()
    else:
        logging.critical("System archictecture unknown.")


def get_os() -> Tuple[str, str]:
    """Gets OS information
    
    Returns:
        OS name
        OS release
    """
    # FIXME: Not working? Returns "Linux" on some systems? On Ubuntu 24.04 it
    # correctly returns "ubuntu".
    os_name = distro.id()
    logging.info(f"OS name: {os_name}")
    os_release = distro.version()
    logging.info(f"OS release: {os_release}")
    return os_name, os_release


class SuperuserCommandNotFound(Exception):
    """Superuser command not found. Install pkexec or sudo or doas"""


def get_superuser_command() -> str:
    if shutil.which('pkexec'):
        return "pkexec"
    elif shutil.which('sudo'):
        return "sudo"
    elif shutil.which('doas'):
        return "doas"
    else:
        raise SuperuserCommandNotFound


@dataclass
class PackageManager:
    """Dataclass to pass around relevant OS context regarding system packages"""
    # Commands
    install: list[str]
    download: list[str]
    remove: list[str]
    query: list[str]

    query_prefix: str

    packages: str
    
    incompatible_packages: str
    # For future expansion:
    # elf_packages: str


def get_package_manager() -> PackageManager | None:
    major_ver = distro.major_version()
    os_name = distro.id()
    logging.debug(f"{os_name=}; {major_ver=}")
    # Check for package manager and associated packages.

    install_command: list[str]
    download_command: list[str]
    remove_command: list[str]
    query_command: list[str]
    query_prefix: str
    packages: str
    incompatible_packages: str

    if shutil.which('apt') is not None:  # debian, ubuntu, & derivatives
        install_command = ["apt", "install", "-y"]
        download_command = ["apt", "install", "--download-only", "-y"]
        remove_command = ["apt", "remove", "-y"]
        query_command =  ["dpkg", "-l"]
        query_prefix = '.i  '
        # Set default package list.
        packages = (
            "binutils wget winbind "  # wine
            "p7zip-full cabextract " # winetricks
            "xdg-utils " # For xdg-mime needed for custom url scheme registration
        )

        # Now set the appimage packages, this has changed over time
        # NOTE: Package names changed together for Ubuntu 24+, Debian 13+, and
        # derivatives. This does not include an exhaustive list of distros that
        # use 'apt', so others will have to be added as users report issues.
        # Ref:
        # - https://askubuntu.com/a/445496
        # - https://en.wikipedia.org/wiki/Linux_Mint
        # - https://en.wikipedia.org/wiki/Elementary_OS
        # - https://github.com/which-distro/os-release/tree/main
        if (
            (os_name == 'debian' and major_ver >= '13')
        ):
            packages += (
                "libfuse3-4 "  # appimages
            )
        elif (
            (os_name == 'ubuntu' and major_ver >= '24')
            or (os_name == 'linuxmint' and major_ver >= '22')
            or (os_name == 'elementary' and major_ver >= '8')
        ):
            packages += (
                "libfuse3-3 "  # appimages
            )
        else:
            packages += (
                "libfuse2 "  # appimages
            )
        incompatible_packages = ""  # appimagelauncher handled separately
    elif shutil.which('dnf') is not None:  # rhel, fedora
        install_command = ["dnf", "install", "-y"]
        download_command = ["dnf", "install", "--downloadonly", "-y"]
        remove_command = ["dnf", "remove", "-y"]
        # Fedora < 41 uses dnf4, while Fedora  41 uses dnf5. The dnf list
        # command is sligtly different between the two.
        # https://discussion.fedoraproject.org/t/after-f41-upgrade-dnf-says-no-packages-are-installed/135391
        # Fedora < 41
        # query_command =  ["dnf", "list", "installed"]
        # Fedora 41
        # query_command =  ["dnf", "list", "--installed"]

        # specifying a format is so we can match exactly on the package name
        query_command =  ["rpm", "-qa", "--qf", "'%{NAME}'"]
        query_prefix = ''
        packages = (
            "fuse fuse-libs "  # appimages
            "mod_auth_ntlm_winbind samba-winbind samba-winbind-clients "  # wine
            "cabextract " # winetricks
            "xdg-utils " # For xdg-mime needed for custom url scheme registration
        )
        incompatible_packages = ""  # appimagelauncher handled separately
    elif shutil.which('zypper') is not None:  # OpenSUSE
        install_command = ["zypper", "--non-interactive", "install"]
        download_command = ["zypper", "download"]
        remove_command = ["zypper", "--non-interactive", "remove"]
        query_command =  ["zypper", "se", "-si"]
        # This could also be a 'i+ | '
        query_prefix = 'i  | '
        packages = (
            "fuse "  # appimages
            "samba wget "  # wine
            "curl gawk grep "  # other
            "7zip cabextract "  # winetricks
            "xdg-utils " # For xdg-mime needed for custom url scheme registration
        )
        incompatible_packages = ""  # appimagelauncher handled separately
    elif shutil.which('apk') is not None:  # alpine
        install_command = ["apk", "--no-interactive", "add"]
        download_command = ["apk", "--no-interactive", "fetch"]
        remove_command = ["apk", "--no-interactive", "del"]
        query_command = ["apk", "list", "-I"]
        query_prefix = ''
        packages = (
            "bash bash-completion "  # bash support
            "gcompat "  # musl to glibc
            #"fuse-common fuse fuse3 "  # appimages
            "wget curl "  # network
            "7zip cabextract " # winetricks
            "samba sed grep gawk bash bash-completion "  # other
            "xdg-utils " # For xdg-mime needed for custom url scheme registration
        )
        incompatible_packages = ""  # appimagelauncher handled separately
    elif shutil.which('pamac') is not None:  # manjaro
        install_command = ["pamac", "install", "--no-upgrade", "--no-confirm"]
        download_command = ["pamac", "install", "--no-upgrade", "--download-only", "--no-confirm"]
        remove_command = ["pamac", "remove", "--no-confirm"]
        query_command =  ["pamac", "list", "-i"]
        query_prefix = ''
        packages = (
            "fuse2 "  # appimages
            "samba wget "  # wine
            "curl gawk grep "  # other
            "7zip cabextract "  # winetricks (7zip used to be called p7zip)
            "xdg-utils " # For xdg-mime needed for custom url scheme registration
        )
        incompatible_packages = ""  # appimagelauncher handled separately
    elif shutil.which('pacman') is not None:  # arch, steamOS
        install_command = ["pacman", "-Syu", "--noconfirm", "--needed"]
        download_command = ["pacman", "-Sw", "-y"]
        remove_command = ["pacman", "-R", "--no-confirm"]
        query_command =  ["pacman", "-Q"]
        query_prefix = ''
        if os_name == "steamos":  # steamOS
            packages = (
                "patch wget sed grep gawk p7zip cabextract samba bc libxml2 curl print-manager "
                "system-config-printer cups-filters nss-mdns foomatic-db-engine foomatic-db-ppds "
                "foomatic-db-nonfree-ppds ghostscript glibc samba extra-rel/apparmor core-rel/libcurl-gnutls "
                "appmenu-gtk-module lib32-libjpeg-turbo qt5-virtualkeyboard wine-staging giflib lib32-giflib libpng "
                "lib32-libpng libldap lib32-libldap gnutls lib32-gnutls mpg123 lib32-mpg123 openal lib32-openal "
                "v4l-utils lib32-v4l-utils libpulse lib32-libpulse libgpg-error lib32-libgpg-error alsa-plugins "
                "lib32-alsa-plugins alsa-lib lib32-alsa-lib libjpeg-turbo lib32-libjpeg-turbo sqlite lib32-sqlite "
                "libxcomposite lib32-libxcomposite libxinerama lib32-libgcrypt libgcrypt lib32-libxinerama ncurses "
                "lib32-ncurses ocl-icd lib32-ocl-icd libxslt lib32-libxslt libva lib32-libva gtk3 lib32-gtk3 "
                "gst-plugins-base-libs lib32-gst-plugins-base-libs vulkan-icd-loader lib32-vulkan-icd-loader "
                "xdg-utils " # For xdg-mime needed for custom url scheme registration
            )
        else:  # arch
            packages = (
                "fuse2 "  # appimages
                "binutils libwbclient samba wget "  # wine
                "7zip cabextract " # winetricks (7zip used to be called pzip then p7zip)
                "openjpeg2 libxcomposite libxinerama "  # display
                "ocl-icd vulkan-icd-loader "  # hardware
                "alsa-plugins gst-plugins-base-libs libpulse openal "  # audio
                "libva mpg123 v4l-utils "  # video
                "libxslt sqlite "  # misc
                "xdg-utils " # For xdg-mime needed for custom url scheme registration
            )
        incompatible_packages = ""  # appimagelauncher handled separately
    elif os_name == "org.freedesktop.platform":
        # Flatpak
        # Dependencies are managed by the flatpak
        install_command = download_command = remove_command = query_command =  ["/usr/bin/true"] 
        query_prefix = ''
        packages = ""
        incompatible_packages = ""
    else:
        # Add more conditions for other package managers as needed.
        logging.critical("Your package manager is not yet supported. Please contact the developers.") 
        return None

    output = PackageManager(
        install=install_command,
        download=download_command,
        query=query_command,
        remove=remove_command,
        incompatible_packages=incompatible_packages,
        packages=packages,
        query_prefix=query_prefix
    )
    logging.debug(f"Package Manager: {output}")
    return output


def query_packages(package_manager: PackageManager, packages, mode="install") -> list[str]: 
    result = None
    missing_packages = []
    conflicting_packages = []

    command = package_manager.query

    try:
        result = run_command(command)
    except Exception as e:
        logging.error(f"Error occurred while executing command: {e}")
    # FIXME: consider raising an exception
    if result is None:
        logging.error("Failed to query packages")
        return []
    package_list = result.stdout

    logging.debug(f"packages to check: {packages}")
    status = {package: "Unchecked" for package in packages}

    for p in packages:
        logging.debug(f"Checking for: {p}")
        l_num = 0
        for line in package_list.split('\n'):
            # logging.debug(f"{line=}")
            l_num += 1
            if package_manager.query[0] == 'dpkg':
                parts = line.strip().split()
                if l_num < 6 or len(parts) < 2:  # skip header, etc.
                    continue
                state = parts[0]
                pkg = parts[1].split(':')[0]  # remove :arch if present
                if pkg == p and state[1] == 'i':
                    if mode == 'install':
                        status[p] = "Installed"
                    elif mode == 'remove':
                        conflicting_packages.append(p)
                        status[p] = 'Conflicting'
                    break
            else:
                package_line_start = f"{package_manager.query_prefix}{p}"
                # For rpm we can match the whole line
                if package_manager.query[0] == 'rpm' and line.strip() == package_line_start: 
                    logging.debug(f"'{p}' installed: {line}")
                    status[p] = "Installed"
                    break
                elif package_manager.query[0] == 'zypper' and mode == "install":
                    # This might be an issue for all OS' however at least on zypper when
                    # the "fuse3" package is installed, it thinks the fuse package is
                    # installed. Solve this by adding whitespace to the startswith
                    package_line_start += " "
                    # zypper also has two (known) possible prefixes 'i  | '
                    # as set in query_prefix and 'i+ | '
                    if (
                        line.strip().startswith(package_line_start)
                        or line.strip().startswith(f"i+ | {p} ")
                    ):
                        logging.debug(f"'{p}' installed: {line}")
                        status[p] = "Installed"
                        break
                elif line.strip().startswith(package_line_start) and mode == "install":
                    logging.debug(f"'{p}' installed: {line}")
                    status[p] = "Installed"
                    break
                elif line.strip().startswith(p) and mode == "remove":
                    conflicting_packages.append(p)
                    status[p] = "Conflicting"
                    break

        if status[p] == "Unchecked":
            if mode == "install":
                missing_packages.append(p)
                status[p] = "Missing"
            elif mode == "remove":
                status[p] = "Not Installed"
        logging.debug(f"{p} status: {status.get(p)}")

    logging.debug(f"Packages status: {status}")

    if mode == "install":
        if missing_packages:
            txt = f"Missing packages: {' '.join(missing_packages)}"
            logging.info(f"{txt}")
        return missing_packages
    elif mode == "remove":
        if conflicting_packages:
            txt = f"Conflicting packages: {' '.join(conflicting_packages)}"
            logging.info(f"Conflicting packages: {txt}")
        return conflicting_packages
    else:
        raise ValueError(f"Invalid query mode: {mode}")


def have_dep(cmd):
    if shutil.which(cmd) is not None:
        return True
    else:
        return False


def check_dialog_version():
    if have_dep("dialog"):
        try:
            result = run_command(["dialog", "--version"])
            if result is None:
                print("Failed to run the 'dialog' command.")
                return None
            version_info = result.stdout.strip()
            if version_info.startswith("Version: "):
                version_info = version_info[len("Version: "):]
            return version_info
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {e.stderr}")
        except FileNotFoundError:
            print("The 'dialog' command is not found. Please ensure it is installed and in your PATH.")
        return None


def test_dialog_version():
    version: Optional[str] = check_dialog_version()

    def parse_date(version):
        try:
            return version.split('-')[1]
        except IndexError:
            return ''

    minimum_version = "1.3-20201126-1"

    logging.debug(f"Current dialog version: {version}")
    if version is not None:
        minimum_version = parse_date(minimum_version)
        current_version = parse_date(version)
        logging.debug(f"Minimum dialog version: {minimum_version}. Installed version: {current_version}.")
        return current_version > minimum_version
    else:
        return None


def remove_appimagelauncher(app: App):
    app.status("Removing AppImageLauncher…")
    pkg = "appimagelauncher"
    package_manager = get_package_manager()
    if package_manager is None:
        app.exit("Failed to find the package manager to uninstall AppImageLauncher.")
    cmd = [app.superuser_command, *package_manager.remove, pkg]
    try:
        logging.debug(f"Running command: {cmd}")
        run_command(cmd)
    except subprocess.CalledProcessError as e:
        if e.returncode == 127:
            logging.error("User cancelled appimagelauncher removal.")
        else:
            logging.error(f"An error occurred: {e}")
            logging.error(f"Command output: {e.output}")
        app.exit(f"Failed to uninstall AppImageLauncher: {e}")
    logging.info("System reboot is required.")
    sys.exit()


def preinstall_dependencies_steamos(superuser_command: str):
    logging.debug("Disabling read only, updating pacman keys…")
    command = [
        superuser_command, "steamos-readonly", "disable", "&&",
        superuser_command, "pacman-key", "--init", "&&",
        superuser_command, "pacman-key", "--populate", "archlinux",
    ]
    return command


def postinstall_dependencies_steamos(superuser_command: str):
    logging.debug("Updating DNS settings & locales, enabling services & read-only system…")
    command = [
        superuser_command, "sed", '-i',
        's/mymachines resolve/mymachines mdns_minimal [NOTFOUND=return] resolve/',
        '/etc/nsswitch.conf', '&&',
        superuser_command, "locale-gen", '&&',
        superuser_command, "systemctl", "enable", "--now", "avahi-daemon", "&&",
        superuser_command, "systemctl", "enable", "--now", "cups", "&&",
        superuser_command, "steamos-readonly", "enable",
    ]
    return command


def postinstall_dependencies_alpine(superuser_command: str) -> list[str]:
    # user = os.getlogin()
    command: list[str] = [
        #superuser_command, "modprobe ", "fuse ", "&& ",
        #superuser_command, "bash ", "-c ", "if \( ! rc-service -e fuse ); then rc-update add fuse boot ", "&& ", 
        #superuser_command, "sed ", "-i ", "'s/#user_allow_other/user_allow_other/g' ", "/etc/fuse.conf ", "&& ", 
        #superuser_command, "addgroup ", "fuse ", "&& ",
        #superuser_command, "adduser ", f"{user} ", "fuse ", "&& ",
        #superuser_command, "bash ", "-c ", "if \( ! rc-service -e fuse ); then rc-service fuse restart ", "&& ", 
    ]
    return command


def preinstall_dependencies(superuser_command: str):
    command = []
    logging.debug("Performing pre-install dependencies…")
    os_name, _ = get_os()
    if os_name == "Steam":
        command = preinstall_dependencies_steamos(superuser_command)
    else:
        logging.debug("No pre-install dependencies required.")
    return command


def postinstall_dependencies(superuser_command: str):
    command = []
    logging.debug("Performing post-install dependencies…")
    os_name, _ = get_os()
    if os_name == "Steam":
        command = postinstall_dependencies_steamos(superuser_command)
    elif os_name == "alpine":
        command = postinstall_dependencies_alpine(superuser_command)
    else:
        logging.debug("No post-install dependencies required.")
    return command


def install_dependencies(app: App, target_version=10):
    if app.conf.skip_install_system_dependencies:
        return

    install_deps_failed = False
    reboot_required = False
    message: Optional[str] = None
    secondary: Optional[str] = None
    command = []
    preinstall_command = []
    install_command = []
    remove_command = []
    postinstall_command = []
    missing_packages = []
    conflicting_packages = []
    package_list = []
    bad_package_list = []

    package_manager = get_package_manager()

    os_name, _ = get_os()

    if not package_manager:
        app.exit(
            f"The script could not determine your {os_name} install's package manager or it is unsupported."
        )

    package_list = package_manager.packages.split()

    bad_package_list = package_manager.incompatible_packages.split()

    logging.debug("Querying packages…")
    missing_packages = query_packages(
        package_manager,
        package_list,
    )
    conflicting_packages = query_packages(
        package_manager,
        bad_package_list,
        mode="remove",
    )

    if missing_packages and conflicting_packages:
        message = f"Your {os_name} computer requires installing and removing some software.\nProceed?"
        secondary = (
            "To continue, the program will attempt to install the following package(s) by using "
            f"'{package_manager.install}':\n{missing_packages}\nand will remove the following package(s) by using "
            f"'{package_manager.remove}':\n{conflicting_packages}"
        )
    elif missing_packages:
        message = f"Your {os_name} computer requires installing some software.\nProceed?"
        secondary = ("To continue, the program will attempt to install the following package(s) by using "
                     f"'{package_manager.install}':\n{missing_packages}")
    elif conflicting_packages:
        message = f"Your {os_name} computer requires removing some software.\nProceed?"
        secondary = ("To continue, the program will attempt to remove the following package(s) by using "
                     f"'{package_manager.remove}':\n{conflicting_packages}")
    else:
        message = None
        secondary = None

    if message is None:
        logging.debug("No missing or conflicting dependencies found.")
    else:
        app.approve_or_exit(message, secondary)

    preinstall_command = preinstall_dependencies(app.superuser_command)

    if missing_packages:
        install_command = package_manager.install + missing_packages
    else:
        logging.debug("No missing packages detected.")

    if conflicting_packages:
        # TODO: Verify with user before executing
        # AppImage Launcher is the only known conflicting package.
        remove_command = package_manager.remove + conflicting_packages
        reboot_required = True
        logging.info("System reboot required.")
    else:
        logging.debug("No conflicting packages detected.")

    postinstall_command = postinstall_dependencies(app.superuser_command)

    if preinstall_command:
        command.extend(preinstall_command)
    if install_command:
        if command:
            command.append('&&')
        command.extend(install_command)
    if remove_command:
        if command:
            command.append('&&')
        command.extend(remove_command)
    if postinstall_command:
        if command:
            command.append('&&')
        command.extend(postinstall_command)
    if not command:  # nothing to run; avoid running empty pkexec command
        if app:
            app.status("All dependencies are met.", 100)
        return

    app.status("Installing dependencies…")
    final_command = [
        # FIXME: Consider switching this back to single quotes
        # (the sed line in alpine post will need to change to double if so)
        f"{app.superuser_command}", 'sh', '-c', '"', *command, '"'
    ]
    command_str = ' '.join(final_command)
    # FIXME: consider how to tell the user which command we're running.
    # When we install on the terminal the user doesn't know what they're sudo'ing
    # logging.info(f"Running command: {command_str}")

    if not install_deps_failed:
        try:
            logging.debug(f"Attempting to run this command: {command_str}")
            run_command(command_str, shell=True)
        except subprocess.CalledProcessError as e:
            if e.returncode == 127:
                logging.error("User cancelled dependency installation.")
            else:
                logging.error(f"An error occurred in install_dependencies(): {e}")
                logging.error(f"Command output: {e.output}")
            install_deps_failed = True


    if reboot_required:
        question = "The system has installed or removed a package that requires a reboot. Do you want to restart now?"
        if app.approve_or_exit(question):
            reboot(app.superuser_command)
        else:
            logging.error("Please reboot then launch the installer again.")
            sys.exit(1)


def ensure_winetricks(
    app: App,
    version=constants.WINETRICKS_VERSION,
    status_messages: bool = True
):
    winetricks_path = Path(app.conf.installer_binary_dir) / "winetricks"

    if winetricks_path.exists():
        # No need to do anything
        return

    # Symlink if using an appimage
    if (
        app.conf.wine_binary_code in ["Recommended", "AppImage"]
        and app.conf.wine_appimage_path is not None
        and app.conf.wine_appimage_path.exists()
    ):
        winetricks_path.symlink_to(app.conf.wine_appimage_path)
        logging.debug("Winetricks symlinked to appimage.")
        return

    # Otherwise download
    if status_messages:
        app.status(f"Installing winetricks v{version}…")
    base_url = "https://codeload.github.com/Winetricks/winetricks/zip/refs/tags"
    zip_name = f"{version}.zip"
    network.logos_reuse_download(
        f"{base_url}/{version}",
        zip_name,
        app.conf.download_dir,
        app=app,
        status_messages=status_messages
    )
    wtzip = f"{app.conf.download_dir}/{zip_name}"
    logging.debug(f"Extracting winetricks script to {winetricks_path}…")
    with zipfile.ZipFile(wtzip) as z:
        for zi in z.infolist():
            if zi.is_dir():
                continue
            zi.filename = Path(zi.filename).name
            if zi.filename == 'winetricks':
                z.extract(zi, path=str(winetricks_path.parent))
                break
    os.chmod(winetricks_path, 0o755)
    logging.debug("Winetricks installed.")


def check_incompatibilities(app: App):
    # Check for AppImageLauncher
    if shutil.which('AppImageLauncher'):
        question_text = "Remove AppImageLauncher? A reboot will be required."
        secondary = (
            "Your system currently has AppImageLauncher installed.\n"
            f"{constants.APP_NAME} is not compatible with AppImageLauncher.\n"
            f"For more information, see: {constants.REPOSITORY_LINK}/issues/114"
        )
        app.approve_or_exit(question_text, secondary)
        remove_appimagelauncher(app)

