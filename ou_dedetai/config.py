import copy
import os
import subprocess
from typing import Any, Optional
from dataclasses import dataclass
import json
import logging
from pathlib import Path

from ou_dedetai import network, utils, constants, wine, system

from ou_dedetai.constants import PROMPT_OPTION_DIRECTORY

@dataclass
class LegacyConfiguration:
    """Configuration and it's keys from before the user configuration class existed.
    
    Useful for one directional compatibility"""
    # Legacy Core Configuration
    FLPRODUCT: Optional[str] = None
    TARGETVERSION: Optional[str] = None
    TARGET_RELEASE_VERSION: Optional[str] = None
    current_logos_version: Optional[str] = None # Unused in new code
    curses_colors: Optional[str] = None
    INSTALLDIR: Optional[str] = None
    # WINETRICKSBIN: Optional[str] = None
    WINEBIN_CODE: Optional[str] = None
    WINE_EXE: Optional[str] = None
    WINECMD_ENCODING: Optional[str] = None
    LOGS: Optional[str] = None
    BACKUPDIR: Optional[str] = None
    LAST_UPDATED: Optional[str] = None # Unused in new code
    RECOMMENDED_WINE64_APPIMAGE_URL: Optional[str] = None # Unused in new code
    LLI_LATEST_VERSION: Optional[str] = None # Unused in new code
    logos_release_channel: Optional[str] = None
    lli_release_channel: Optional[str] = None

    # Legacy Extended Configuration
    APPIMAGE_LINK_SELECTION_NAME: Optional[str] = None
    APPDIR_BINDIR: Optional[str] = None
    CHECK_UPDATES: Optional[bool] = None
    CONFIG_FILE: Optional[str] = None
    CUSTOMBINPATH: Optional[str] = None
    DEBUG: Optional[bool] = None
    DELETE_LOG: Optional[str] = None
    DIALOG: Optional[str] = None # Unused in new code
    LOGOS_LOG: Optional[str] = None
    wine_log: Optional[str] = None
    LOGOS_EXE: Optional[str] = None # Unused in new code
    # This is the logos installer executable name (NOT path)
    LOGOS_EXECUTABLE: Optional[str] = None
    LOGOS_VERSION: Optional[str] = None
    # This wasn't overridable in the bash version of this installer (at 554c9a6),
    # nor was it used in the python version (at 8926435)
    # LOGOS64_MSI: Optional[str]
    LOGOS64_URL: Optional[str] = None
    SELECTED_APPIMAGE_FILENAME: Optional[str] = None
    SKIP_DEPENDENCIES: Optional[bool] = None
    use_python_dialog: Optional[str] = None
    VERBOSE: Optional[bool] = None
    WINEDEBUG: Optional[str] = None
    WINEDLLOVERRIDES: Optional[str] = None
    WINEPREFIX: Optional[str] = None
    WINESERVER_EXE: Optional[str] = None

    @classmethod
    def bool_keys(cls) -> list[str]:
        """Returns a list of keys that are of type bool"""
        return [
            "VERBOSE",
            "SKIP_DEPENDENCIES",
            "DEBUG",
            "CHECK_UPDATES"
        ]

    @classmethod
    def config_file_path(cls) -> str:
        return os.getenv("CONFIG_FILE") or constants.DEFAULT_CONFIG_PATH

    @classmethod
    def load(cls) -> "LegacyConfiguration":
        """Find the relevant config file and load it"""
        # Update config from CONFIG_FILE.
        config_file_path = LegacyConfiguration.config_file_path()
        # This moves the first legacy config to the new location
        if not utils.file_exists(config_file_path):
            for legacy_config in constants.LEGACY_CONFIG_FILES:
                if utils.file_exists(legacy_config):
                    Path(config_file_path).parent.mkdir(parents=True, exist_ok=True)
                    os.rename(legacy_config, config_file_path)
                    break
        # This may be a config that used to be in the legacy location
        # Now it's all in the same location
        return LegacyConfiguration.load_from_path(config_file_path)

    @classmethod
    def load_from_path(cls, config_file_path: str) -> "LegacyConfiguration":
        config_dict: dict[str, str] = {}
        
        if not Path(config_file_path).exists():
            pass
        elif config_file_path.endswith('.json'):
            try:
                with open(config_file_path, 'r') as config_file:
                    cfg = json.load(config_file)

                for key, value in cfg.items():
                    config_dict[key] = value
            except TypeError as e:
                logging.error("Error opening Config file.")
                logging.error(e)
                raise e
            except FileNotFoundError:
                logging.info(f"No config file not found at {config_file_path}")
            except json.JSONDecodeError as e:
                logging.error("Config file could not be read.")
                logging.error(e)
                raise e
        elif config_file_path.endswith('.conf'):
            # Legacy config from bash script.
            logging.info("Reading from legacy config file.")
            with open(config_file_path, 'r') as config_file:
                for line in config_file:
                    line = line.strip()
                    if len(line) == 0:  # skip blank lines
                        continue
                    if line[0] == '#':  # skip commented lines
                        continue
                    parts = line.split('=')
                    if len(parts) == 2:
                        value = parts[1].strip('"').strip("'")  # remove quotes
                        vparts = value.split('#')  # get rid of potential comment
                        if len(vparts) > 1:
                            value = vparts[0].strip().strip('"').strip("'")
                        config_dict[parts[0]] = value

        # Now restrict the key values pairs to just those found in LegacyConfiguration
        output: dict = {}
        config_env = LegacyConfiguration.load_from_env().__dict__
        # Now update from ENV
        for var, env_var in config_env.items():
            if env_var is not None:
                output[var] = env_var
            elif var in config_dict:
                if var in LegacyConfiguration.bool_keys():
                    output[var] = utils.parse_bool(config_dict[var])
                else:
                    output[var] = config_dict[var]

        # Populate the path this config was loaded from
        output["CONFIG_FILE"] = config_file_path

        return LegacyConfiguration(**output)

    @classmethod
    def load_from_env(cls) -> "LegacyConfiguration":
        output: dict = {}
        # Now update from ENV
        for var in LegacyConfiguration().__dict__.keys():
            env_var = os.getenv(var)
            if env_var is not None:
                if var in LegacyConfiguration.bool_keys():
                    output[var] = utils.parse_bool(env_var)
                else:
                    output[var] = env_var
        return LegacyConfiguration(**output)


@dataclass
class EphemeralConfiguration:
    """A set of overrides that don't need to be stored.

    Populated from environment/command arguments/etc

    Changes to this are not saved to disk, but remain while the program runs
    """
    
    # See naming conventions in Config
    
    # Start user overridable via env or cli arg
    installer_binary_dir: Optional[str]
    install_dir: Optional[str]
    wineserver_binary: Optional[str]
    faithlife_product_version: Optional[str]
    faithlife_installer_name: Optional[str]
    faithlife_installer_download_url: Optional[str]
    log_level: Optional[str | int]
    app_log_path: Optional[str]
    app_wine_log_path: Optional[str]
    """Path to log wine's output to"""

    install_dependencies_skip: Optional[bool]
    """Whether to skip installing system package dependencies"""

    wine_dll_overrides: Optional[str]
    """Corresponds to wine's WINEDLLOVERRIDES"""
    wine_debug: Optional[str]
    """Corresponds to wine's WINEDEBUG"""
    wine_prefix: Optional[str]
    """Corresponds to wine's WINEPREFIX"""
    wine_output_encoding: Optional[str]
    """Override for what encoding wine's output is using"""

    # FIXME: seems like the wine appimage logic can be simplified
    wine_appimage_link_file_name: Optional[str]
    """Symlink file name to the active wine appimage."""

    wine_appimage_path: Optional[str]
    """Path to the selected appimage"""

    # FIXME: consider using PATH instead? (and storing this legacy env in PATH for this process)
    custom_binary_path: Optional[str]
    """Additional path to look for when searching for binaries."""

    delete_log: Optional[bool]
    """Whether to clear the log on startup"""

    check_updates_now: Optional[bool]
    """Whether or not to check updates regardless of if one's due"""    

    # Start internal values
    config_path: str
    """Path this config was loaded from"""

    assume_yes: bool = False
    """Whether to assume yes to all prompts or ask the user
    
    Useful for non-interactive installs"""

    quiet: bool = False
    """Whether or not to output any non-error messages"""

    dialog: Optional[str] = None
    """Override if we want to select a specific type of front-end
    
    Accepted values: tk (GUI), curses (TUI), cli (CLI)"""

    wine_args: Optional[list[str]] = None
    """Arguments when running wine from cli"""

    terminal_app_prefer_dialog: Optional[bool] = None

    # Start of values just set via cli arg
    faithlife_install_passive: bool = False
    app_run_as_root_permitted: bool = False
    agreed_to_faithlife_terms: bool = False
    """The user expressed clear agreement with faithlife's terms.
    Normally the MSI would prompt for this as well.

    DO NOT set this unless clear beyond a reasonable doubt the user knows
    what they're doing - agreeing to https://faithlife.com/terms
    """

    @classmethod
    def from_legacy(cls, legacy: LegacyConfiguration) -> "EphemeralConfiguration":
        log_level = None
        wine_debug = legacy.WINEDEBUG
        if legacy.DEBUG:
            log_level = logging.DEBUG
            # FIXME: shouldn't this leave it untouched or fall back to default: `fixme-all,err-all`?
            wine_debug = ""
        elif legacy.VERBOSE:
            log_level = logging.INFO
            wine_debug = ""
        delete_log = None
        if legacy.DELETE_LOG is not None:
            delete_log = utils.parse_bool(legacy.DELETE_LOG)
        config_file = constants.DEFAULT_CONFIG_PATH
        if legacy.CONFIG_FILE is not None:
            config_file = legacy.CONFIG_FILE
        terminal_app_prefer_dialog = None
        if legacy.use_python_dialog is not None:
            terminal_app_prefer_dialog = utils.parse_bool(legacy.use_python_dialog)
        install_dir = None
        if legacy.INSTALLDIR is not None:
            install_dir = str(Path(os.path.expanduser(legacy.INSTALLDIR)).absolute())
        return EphemeralConfiguration(
            installer_binary_dir=legacy.APPDIR_BINDIR,
            wineserver_binary=legacy.WINESERVER_EXE,
            custom_binary_path=legacy.CUSTOMBINPATH,
            faithlife_product_version=legacy.LOGOS_VERSION,
            faithlife_installer_name=legacy.LOGOS_EXECUTABLE,
            faithlife_installer_download_url=legacy.LOGOS64_URL,
            log_level=log_level,
            wine_debug=wine_debug,
            wine_dll_overrides=legacy.WINEDLLOVERRIDES,
            wine_prefix=legacy.WINEPREFIX,
            app_wine_log_path=legacy.wine_log,
            app_log_path=legacy.LOGOS_LOG,
            config_path=config_file,
            check_updates_now=legacy.CHECK_UPDATES,
            delete_log=delete_log,
            install_dependencies_skip=legacy.SKIP_DEPENDENCIES,
            wine_appimage_link_file_name=legacy.APPIMAGE_LINK_SELECTION_NAME,
            wine_appimage_path=legacy.SELECTED_APPIMAGE_FILENAME,
            wine_output_encoding=legacy.WINECMD_ENCODING,
            terminal_app_prefer_dialog=terminal_app_prefer_dialog,
            dialog=legacy.DIALOG,
            install_dir=install_dir
        )

    @classmethod
    def load(cls) -> "EphemeralConfiguration":
        return EphemeralConfiguration.from_legacy(LegacyConfiguration.load())

    @classmethod
    def load_from_path(cls, path: str) -> "EphemeralConfiguration":
        return EphemeralConfiguration.from_legacy(LegacyConfiguration.load_from_path(path))


@dataclass
class PersistentConfiguration:
    """This class stores the options the user chose

    Normally shouldn't be used directly, as it's types may be None,
    doesn't handle updates. Use through the `App`'s `Config` instead.
    
    Easy reading to/from JSON and supports legacy keys
    
    These values should be stored across invocations
    
    MUST be saved explicitly
    """

    # See naming conventions in Config

    faithlife_product: Optional[str] = None
    faithlife_product_version: Optional[str] = None
    faithlife_product_release: Optional[str] = None
    faithlife_product_logging: Optional[bool] = None
    install_dir: Optional[str] = None
    wine_binary: Optional[str] = None
    # This is where to search for wine
    # wine_binary_code: Optional[str] = None
    backup_dir: Optional[str] = None

    # Color to use in curses. Either "System", "Logos", "Light", or "Dark"
    curses_color_scheme: Optional[str] = None
    # Faithlife's release channel. Either "stable" or "beta"
    faithlife_product_release_channel: str = "stable"
    # The Installer's release channel. Either "stable" or "beta"
    app_release_channel: str = "stable"

    _legacy: Optional[LegacyConfiguration] = None
    """A Copy of the legacy configuration.
    
    Merge this when writing.
    Kept just in case the user wants to go back to an older installer version
    """

    @classmethod
    def load_from_path(cls, config_file_path: str) -> "PersistentConfiguration":
        # First read in the legacy configuration
        legacy = LegacyConfiguration.load_from_path(config_file_path)
        new_config: PersistentConfiguration = PersistentConfiguration.from_legacy(legacy) 

        new_keys = new_config.__dict__.keys()

        config_dict = new_config.__dict__

        # Check to see if this config is actually "legacy"
        if len([k for k, v in legacy.__dict__.items() if v is not None]) > 1:
            config_dict["_legacy"] = legacy

        if Path(config_file_path).exists():
            if config_file_path.endswith('.json'):
                with open(config_file_path, 'r') as config_file:
                    cfg = json.load(config_file)

                for key, value in cfg.items():
                    if key in new_keys:
                        config_dict[key] = value
            else:
                logging.info("Not reading new values from non-json config")
        else:
            logging.info("Not reading new values from non-existent config")

        # Now override with values from ENV
        config_env = PersistentConfiguration.from_legacy(LegacyConfiguration.load_from_env()) 
        for k, v in config_env.__dict__.items():
            if v is not None:
                config_dict[k] = v

        return PersistentConfiguration(**config_dict)

    @classmethod
    def from_legacy(cls, legacy: LegacyConfiguration) -> "PersistentConfiguration":
        faithlife_product_logging = None
        if legacy.LOGS is not None:
            faithlife_product_logging = utils.parse_bool(legacy.LOGS)
        install_dir = None
        if legacy.INSTALLDIR is not None:
            install_dir = str(Path(os.path.expanduser(legacy.INSTALLDIR)).absolute())
        return PersistentConfiguration(
            faithlife_product=legacy.FLPRODUCT,
            backup_dir=legacy.BACKUPDIR,
            curses_color_scheme=legacy.curses_colors,
            faithlife_product_release=legacy.TARGET_RELEASE_VERSION,
            faithlife_product_release_channel=legacy.logos_release_channel or 'stable',
            faithlife_product_version=legacy.TARGETVERSION,
            install_dir=install_dir,
            app_release_channel=legacy.lli_release_channel or 'stable',
            wine_binary=legacy.WINE_EXE,
            # wine_binary_code=legacy.WINEBIN_CODE,
            faithlife_product_logging=faithlife_product_logging,
            _legacy=legacy
        )

    def _as_dict(self) -> dict[str, Any]:
        # Copy the values into a flat structure for easy json dumping
        output = copy.deepcopy(self.__dict__)
        # Merge the legacy dictionary if present
        if self._legacy is not None:
            output |= self._legacy.__dict__
            # Don't save DIALOG into the config
            if os.getenv("DIALOG"):
                del output["DIALOG"]
        
        # Remove all keys starting with _ (to remove legacy from the saved blob)
        for k in list(output.keys()):
            if (
                k.startswith("_")
                or output[k] is None
                or k == "CONFIG_FILE"
            ):
                del output[k]
        if self.install_dir is not None:
            # Ensure all paths stored are relative to install_dir
            for k, v in output.items():
                if k in ["install_dir", "INSTALLDIR"]:
                    if v is not None:
                        output[k] = str(v)
                    continue
                if (isinstance(v, str) and v.startswith(self.install_dir)): 
                    output[k] = utils.get_relative_path(v, self.install_dir)
        return output

    def write_config(self) -> None:
        config_file_path = LegacyConfiguration.config_file_path()
        output = self._as_dict()

        def write_json_file(config_file_path: str) -> None:
            logging.info(f"Writing config to {config_file_path}")
            os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
            try:
                with open(config_file_path, 'w') as config_file:
                    # Write this into a string first to avoid partial writes
                    # if encoding fails (which it shouldn't)
                    json_str = json.dumps(output, indent=4, sort_keys=True)
                    config_file.write(json_str)
                    config_file.write('\n')
            except IOError as e:
                logging.error(f"Error writing to file {config_file_path}: {e}")
                # Continue, the installer can still operate even if it fails to write.

        if self.install_dir is not None:
            portable_config_path = os.path.expanduser(self.install_dir + f"/{constants.BINARY_NAME}.json") 
            write_json_file(portable_config_path)

        write_json_file(config_file_path)

# Needed this logic outside this class too for before when the app is initialized
def get_wine_prefix_path(install_dir: str) -> str:
    return f"{install_dir}/data/wine64_bottle"


def get_wine_user(wine_prefix: str) -> Optional[str]:
    users_path = f"{wine_prefix}/drive_c/users"
    if not os.path.exists(users_path):
        return None
    # Cache a successful result (as it goes out to the fs)
    users = os.listdir(users_path)
    try:
        users.remove("Public")
    except ValueError:
        pass
    if users:
        return users[0]
    return None


def get_appdata_dir(
    wine_prefix: str,
    wine_user: str,
) -> str:
    return f'{wine_prefix}/drive_c/users/{wine_user}/AppData/'


def get_logos_appdata_dir(
    wine_prefix: str,
    wine_user: str,
    faithlife_product: str
) -> str:
    appdata = get_appdata_dir(wine_prefix=wine_prefix, wine_user=wine_user)
    return f'{appdata}/Local/{faithlife_product}'


def get_logos_user_id(
    logos_appdata_dir: str
) -> Optional[str]:
    logos_data_path = Path(logos_appdata_dir) / "Data"
    contents = os.listdir(logos_data_path)
    children = [logos_data_path / child for child in contents]
    file_children = [child for child in children if child.is_dir()]
    if file_children and len(file_children) > 0:
        return file_children[0].name
    else:
        return None

class Config:
    """Set of configuration values. 
    
    If the user hasn't selected a particular value yet, they will be prompted in the UI.
    """

    # Naming conventions:
    # Use `dir` instead of `directory`
    # Use snake_case
    # prefix with faithlife_ if it's theirs
    # prefix with app_ if it's ours (and otherwise not clear)
    # prefix with wine_ if it's theirs
    # suffix with _binary if it's a linux binary
    # suffix with _exe if it's a windows binary
    # suffix with _path if it's a file path
    # suffix with _file_name if it's a file's name (with extension)

    # Storage for the keys
    _raw: PersistentConfiguration

    # Overriding programmatically generated values from ENV
    _overrides: EphemeralConfiguration

    _network: network.NetworkRequests

    # Start Cache of values unlikely to change during operation.
    # i.e. filesystem traversals
    _wine_user: Optional[str] = None
    _wine64_path: Optional[str] = None
    _download_dir: Optional[str] = None
    _user_download_dir: Optional[str] = None
    _wine_output_encoding: Optional[str] = None
    _installed_faithlife_product_release: Optional[str] = None
    _wine_binary_files: Optional[list[str]] = None
    _wine_appimage_files: Optional[list[str]] = None

    # Start constants
    _curses_color_scheme_valid_values = ["System", "Light", "Dark", "Logos"]

    # Singleton logic, this enforces that only one config object exists at a time.
    def __new__(cls, *args, **kwargs) -> "Config":
        if not hasattr(cls, '_instance'):
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance

    def __init__(self, ephemeral_config: EphemeralConfiguration, app) -> None:
        from ou_dedetai.app import App
        self.app: "App" = app
        self._raw = PersistentConfiguration.load_from_path(ephemeral_config.config_path)
        self._overrides = ephemeral_config

        self._network = self._create_network_requests_with_hook()
        logging.debug("Current persistent config:")
        for k, v in self._raw.__dict__.items():
            logging.debug(f"{k}: {v}")
        logging.debug("Current ephemeral config:")
        for k, v in self._overrides.__dict__.items():
            logging.debug(f"{k}: {v}")
        logging.debug("Current network cache:")
        for k, v in self._network._cache.__dict__.items():
            logging.debug(f"{k}: {v}")
        logging.debug("End config dump")

    def _create_network_requests_with_hook(self) -> network.NetworkRequests:
        def _network_cache_hook():
            self.app._config_updated_event.set()

        return network.NetworkRequests(
            self._overrides.check_updates_now,
            hook=_network_cache_hook
        )
 
    def _ask_if_not_found(
        self,
        parameter: str,
        question: str,
        options: list[str],
        dependent_parameters: Optional[list[str]] = None
    ) -> str:  
        if not getattr(self._raw, parameter):
            if dependent_parameters is not None:
                for dependent_config_key in dependent_parameters:
                    setattr(self._raw, dependent_config_key, None)
            answer = self.app.ask(question, options)
            # Use the setter on this class if found, otherwise set in self._user
            if getattr(Config, parameter) and getattr(Config, parameter).fset is not None:
                getattr(Config, parameter).fset(self, answer)
            else:
                setattr(self._raw, parameter, answer)
                self._write()
        # parameter given should be a string
        return str(getattr(self._raw, parameter))

    def _write(self) -> None:
        """Writes configuration to file and lets the app know something changed"""
        self._raw.write_config()
        self.app._config_updated_event.set()

    def _relative_from_install_dir(self, path: Path | str) -> str:
        """Takes in a possibly absolute path under install dir and turns it into an
        relative path if it is

        Args:
            path - can be absolute or relative to install dir
        
        Returns:
            path - absolute
        """
        output = str(path)
        if Path(path).is_absolute() and output.startswith(self.install_dir):
            output = output[len(self.install_dir):].lstrip("/")
        return output

    def _absolute_from_install_dir(self, path: Path | str) -> str:
        """Takes in a possibly relative path under install dir and turns it into an
        absolute path

        Args:
            path - can be absolute or relative to install dir
        
        Returns:
            path - absolute
        """
        if not Path(path).is_absolute():
            return str(Path(self.install_dir) / path)
        return str(path)

    def reload(self):
        """Re-loads the configuration from disk"""
        self._raw = PersistentConfiguration.load_from_path(self._overrides.config_path)
        self._network = self._create_network_requests_with_hook()
        # Also clear out our cached values
        self._logos_exe = self._download_dir = self._wine_output_encoding = None
        self._installed_faithlife_product_release = self._wine_binary_files = None
        self._wine_appimage_files = self._wine_user = None
        self._wine64_path = self._user_download_dir = None

        self.app._config_updated_event.set()

    @property
    def config_file_path(self) -> str:
        return LegacyConfiguration.config_file_path()

    @property
    def faithlife_product(self) -> str:
        question = "Choose which FaithLife product the script should install: "
        options = constants.FAITHLIFE_PRODUCTS
        return self._ask_if_not_found(
            "faithlife_product",
            question,
            options,
            [
                "faithlife_product_version",
                "faithlife_product_release"
            ]
        )

    @faithlife_product.setter
    def faithlife_product(self, value: Optional[str]):
        if self._raw.faithlife_product != value:
            self._raw.faithlife_product = value
            # Reset dependent variables
            self.faithlife_product_version = None # type: ignore[assignment]

            self._write()

    @property
    def faithlife_product_version(self) -> str:
        if self._overrides.faithlife_product_version is not None:
            return self._overrides.faithlife_product_version
        if self._raw.faithlife_product_version is not None:
            return self._raw.faithlife_product_version
        # The only version we presently support is 10 - so set it.
        self.faithlife_product_version = "10"
        return self.faithlife_product_version
        # Keep following in case we need to prompt for additional versions in the future
        #question = f"Which version of {self.faithlife_product} should the script install?: "
        #options = constants.FAITHLIFE_PRODUCT_VERSIONS
        #return self._ask_if_not_found("faithlife_product_version", question, options, [])

    @faithlife_product_version.setter
    def faithlife_product_version(self, value: Optional[str]):
        if self._raw.faithlife_product_version != value:
            self._raw.faithlife_product_version = value
            # Set dependents
            self._raw.faithlife_product_release = None
            # Install Dir has the name of the product and it's version. Reset it too
            if self._overrides.install_dir is None:
                self._raw.install_dir = None
            # While different versions have different wine version requirements,
            # In order to support WINE_EXE we shouldn't clobber here.
            # self._raw.wine_binary = None
            # self._raw.wine_binary_code = None

            self._write()

    @property
    def faithlife_product_releases(self) -> list[str]:
        return self._network.faithlife_product_releases(
            product=self.faithlife_product,
            version=self.faithlife_product_version,
            channel=self.faithlife_product_release_channel
        )

    @property
    def faithlife_product_release(self) -> str:
        question = (
            f"Which version of {self.faithlife_product} {self.faithlife_product_version} do you want to install?: "
        )
        options = self.faithlife_product_releases
        return self._ask_if_not_found("faithlife_product_release", question, options)

    @faithlife_product_release.setter
    def faithlife_product_release(self, value: Optional[str]):
        if self._raw.faithlife_product_release != value:
            self._raw.faithlife_product_release = value
            # Reset dependents
            self._wine_binary_files = None
            self._write()

    @property
    def faithlife_product_icon_path(self) -> str:
        return str(constants.APP_IMAGE_DIR / f"{self.faithlife_product}-128-icon.png")

    @property
    def faithlife_product_logging(self) -> bool:
        """Whether or not the installed faithlife product is configured to log"""
        if self._raw.faithlife_product_logging is not None:
            return self._raw.faithlife_product_logging
        return False
    
    @faithlife_product_logging.setter
    def faithlife_product_logging(self, value: bool):
        if self._raw.faithlife_product_logging != value:
            self._raw.faithlife_product_logging = value
            self._write()

    @property
    def faithlife_installer_name(self) -> str:
        if self._overrides.faithlife_installer_name is not None:
            return self._overrides.faithlife_installer_name
        return f"{self.faithlife_product}_v{self.faithlife_product_release}-x64.msi"

    @property
    def faithlife_installer_download_url(self) -> str:
        if self._overrides.faithlife_installer_download_url is not None:
            return self._overrides.faithlife_installer_download_url
        after_version_url_part = "/Verbum/" if self.faithlife_product == "Verbum" else "/"
        return f"https://downloads.logoscdn.com/LBS{self.faithlife_product_version}{after_version_url_part}Installer/{self.faithlife_product_release}/{self.faithlife_product}-x64.msi"

    @property
    def faithlife_product_release_channel(self) -> str:
        return self._raw.faithlife_product_release_channel

    @property
    def app_release_channel(self) -> str:
        return self._raw.app_release_channel

    @property
    def winetricks_binary(self) -> str:
        """Download winetricks if it doesn't exist"""
        from ou_dedetai import system
        # Path is now static, the installer puts a symlink here if we're using appimage
        winetricks_path = Path(self.installer_binary_dir) / "winetricks"
    
        system.ensure_winetricks(
            app=self.app,
            status_messages=False
        )

        return self._absolute_from_install_dir(winetricks_path)

    @property
    def install_dir_default(self) -> str:
        return f"{constants.DATA_HOME}/{constants.BINARY_NAME}"

    @property
    def install_dir(self) -> str:
        if self._overrides.install_dir:
            return self._overrides.install_dir
        default = self.install_dir_default
        question = f"Where should {self.faithlife_product} files be installed to?: "
        options = [default, PROMPT_OPTION_DIRECTORY]
        output = self._ask_if_not_found("install_dir", question, options)
        return output
    
    @install_dir.setter
    def install_dir(self, value: Optional[str | Path]):
        if value is not None:
            value = str(Path(value).absolute())
        if self._raw.install_dir != value:
            self._raw.install_dir = value
            # Reset cache that depends on install_dir
            self._wine_appimage_files = None
            self._write()

    @property
    # This used to be called APPDIR_BINDIR
    def installer_binary_dir(self) -> str:
        if self._overrides.installer_binary_dir is not None:
            return self._overrides.installer_binary_dir
        return f"{self.install_dir}/data/bin"

    @property
    def _logos_appdata_dir(self) -> Optional[str]:
        """Path to the user's Logos installation under AppData"""
        # We don't want to prompt the user in this function
        if (
            self._raw.faithlife_product is None
            or self._raw.install_dir is None
        ):
            return None
        wine_user = self.wine_user
        if wine_user is None:
            return None
        return get_logos_appdata_dir(
            self.wine_prefix,
            wine_user,
            self.faithlife_product
        )

    @property
    def _faithlife_logs_dir(self) -> Optional[str]:
        """Path to the directory containing faithlife logs"""
        # We don't want to prompt the user in this function
        wine_user = self.wine_user
        if (
            wine_user is None
            or self._raw.faithlife_product is None
            or self._raw.install_dir is None
        ):
            return None
        appdata = get_appdata_dir(
            self.wine_prefix,
            wine_user,
        )
        return f'{appdata}/Local/Faithlife/Logs/{self.faithlife_product}'

    @property
    def _faithlife_crash_log(self) -> Optional[str]:
        """Path to the LogosCrash.log or VerbumCrash.log respectively"""
        faithlife_logs = self._faithlife_logs_dir
        if not faithlife_logs or self._raw.faithlife_product is None:
            return None
        # FIXME: Confirm Verbum's Crash log has this name - not aware of a Verbum crash right now
        # to confirm this.
        return f"{faithlife_logs}/{self._raw.faithlife_product}Crash.log"

    @property
    def _logos_user_id(self) -> Optional[str]:
        """Name of the Logos user id throughout the app"""
        logos_appdata_dir = self._logos_appdata_dir
        if logos_appdata_dir is None:
            return None
        return get_logos_user_id(logos_appdata_dir)

    @property
    # This used to be called WINEPREFIX
    def wine_prefix(self) -> str:
        if self._overrides.wine_prefix is not None:
            return self._overrides.wine_prefix
        return get_wine_prefix_path(self.install_dir)

    @property
    def wine_rootfs(self) -> str:
        """This path may or may not exist"""
        return f"{self.install_dir}/{self.wine_rootfs_relative}"
    
    @property
    def wine_rootfs_relative(self) -> str:
        """This path may or may not exist"""
        return "wine_rootfs/"

    @property
    def wine_path_in_rootfs(self) -> str:
        wine_opt = Path(self.wine_rootfs) / "opt"
        # Glob on the next folder as it might be wine-staging, or wine-stable, ect.
        return str(next(wine_opt.glob("wine*")) / "bin" / "wine") #noqa: E501

    @property
    def is_wine_binary_in_wine_rootfs(self) -> bool:
        return self.wine_binary.startswith(self.wine_rootfs_relative) or self.wine_binary.startswith(self.wine_rootfs)

    @property
    def wine_binary(self) -> str:
        """Returns absolute path to the wine binary"""
        output = self._raw.wine_binary
        if output is None:
            question = (
                f"Which Wine AppImage or binary should the script use to install {self.faithlife_product} "
                f"v{self.faithlife_product_version} in {self.install_dir}?: "
            )
            options = utils.get_wine_options(self.app)

            choice = self.app.ask(question, options)

            output = choice
            self.wine_binary = choice
        # Return the full path so we the callee doesn't need to think about it
        if (
            self._raw.wine_binary is not None 
            and not Path(self._raw.wine_binary).exists() 
            and (Path(self.install_dir) / self._raw.wine_binary).exists()
        ):
            return str(Path(self.install_dir) / self._raw.wine_binary)
        # Output a warning if the path doesn't exist and isn't relative to
        # the install dir.
        # In the case of appimage, this won't exist for part of the 
        # installation, but still is valid. And the appimage uses a relative
        # path or an absolute that's relative to the install dir
        if (
            not Path(output).exists()
            and Path(output).is_absolute()
            and not Path(output).is_relative_to(self.install_dir)
        ):
            logging.warning(f"Wine binary {output} doesn't exist")
        return output

    @wine_binary.setter
    def wine_binary(self, value: str):
        """Takes in a path to the wine binary and stores it as relative for storage"""
        if value in [
            constants.RECOMMENDED_WINE_APPIMAGE_SIGIL,
            constants.RECOMMENDED_WINE_TARBALL_SIGIL,
            constants.UNTESTED_WINE_STABLE_APPIMAGE_SIGIL,
            constants.UNTESTED_WINE_STAGING_APPIMAGE_SIGIL,
            constants.UNTESTED_WINE_DEVELOPMENT_APPIMAGE_SIGIL,
        ]:
            # We handle this case in the installer.
            # Don't like how this value (which should only be a path to a wine binary)
            # can sometimes be a download option - i.e. one that doesn't exist yet.
            # But that's a problem for another day.
            pass

        # Make the path absolute for comparison
        relative = self._relative_from_install_dir(value)
        # FIXME: consider this, it doesn't work at present as the wine_binary may be an
        # appimage that hasn't been downloaded yet
        # aboslute = self._absolute_from_install_dir(value)
        # if not Path(aboslute).is_file():
        #     raise ValueError("Wine Binary path must be a valid file")

        if self._raw.wine_binary != relative:
            self._raw.wine_binary = relative
            # Reset dependents
            # self._raw.wine_binary_code = None
            self._overrides.wine_appimage_path = None
            self._wine64_path = None
            self._write()

    @property
    def wine_binary_files(self) -> list[str]:
        if self._wine_binary_files is None:
            self._wine_binary_files = utils.find_wine_binary_files(
                self.app,
                self._raw.faithlife_product_release
            )
        return self._wine_binary_files

    @property
    def wine_app_image_files(self) -> list[str]:
        if self._wine_appimage_files is None:
            self._wine_appimage_files = utils.find_appimage_files(self.app)
        return self._wine_appimage_files

    @property
    def wine64_binary(self) -> str:
        # Use cache if available
        if self._wine64_path:
            return self._wine64_path
        # Some packaging uses wine64 for the 64bit binary (like wine 10 on debian),
        # others use wine (like wine 10.2 on debian)
        wine64_path = Path(self.wine_binary).parent / 'wine64'
        wine_path = Path(self.wine_binary)
        # Prefer wine64 if it exists
        if wine64_path.exists():
            self._wine64_path = str(wine64_path)
            return str(wine64_path)
        if not wine_path.exists():
            logging.warning(f"Wine exe path doesn't exist: {wine_path}")
            # Return it anyways, hopefully doesn't matter.
            # Don't cache this just in case it changes to a 32bit binary while we're
            # running
            return str(wine_path)
        # Use the file binary if found to check the architecture type
        try:
            file_output = subprocess.check_output(
                ["file", "-bL", str(wine_path)],
                env=system.fix_ld_library_path(None),
                encoding="utf-8"
            ).strip()
            if file_output.startswith("ELF 64-bit LSB pie executable,"):
                # Confirmed wine binary is 64 bit
                self._wine64_path = str(wine_path)
            elif file_output.startswith("ELF 32-bit LSB pie executable,"):
                # Woah there, we only have a 32 bit binary.
                self.app.exit("Could not find a 64 bit wine binary, please install a 64bit wine")
            else:
                # We don't want to fail here since file might behave differently on
                # different systems or maybe different on BSD
                # better to just let it go this time. 
                # If it really is a problem, the user will hit other errors later on
                # And this will be in the log when we support.
                logging.warning(
                    "Could not parse architecture from wine binary "
                    f"({wine_path})"
                    f": {file_output}\n"
                    "Assuming it is the right architecture"
                )
        except Exception as e:
            logging.warning(f"Failed to check wine binary architecture: {e}")
        # Update the cache and return
        self._wine64_path = str(wine_path)
        return str(wine_path)
    
    @property
    # This used to be called WINESERVER_EXE
    def wineserver_binary(self) -> str:
        return str(Path(self.wine_binary).parent / 'wineserver')

    # FIXME: seems like the logic around wine appimages can be simplified
    # Should this be folded into wine_binary?
    @property
    def wine_appimage_path(self) -> Optional[Path]:
        """Path to the wine appimage
        
        Returns:
            Path if wine is set to use an appimage, otherwise returns None"""
        if self._overrides.wine_appimage_path is not None:
            return Path(self._absolute_from_install_dir(self._overrides.wine_appimage_path)) 
        if self.wine_binary.lower().endswith(".appimage"):
            return Path(self._absolute_from_install_dir(self.wine_binary))
        return None
    
    @wine_appimage_path.setter
    def wine_appimage_path(self, value: Optional[str | Path]) -> None:
        if isinstance(value, Path):
            value = str(value)
        if self._overrides.wine_appimage_path != value:
            self._overrides.wine_appimage_path = value
            # Reset dependents

    @property
    def wine_appimage_link_file_name(self) -> str:
        if self._overrides.wine_appimage_link_file_name is not None:
            return self._overrides.wine_appimage_link_file_name
        return 'selected_wine.AppImage'

    @property
    def wine_download_url(self) -> str:
        """URL to download the specified wine binary
        
        Talks to the network if required"""
        if self.wine_binary == constants.UNTESTED_WINE_STABLE_APPIMAGE_SIGIL:
            return self._network.wine_appimage_upstream_url("continuous-stable")
        elif self.wine_binary == constants.UNTESTED_WINE_STAGING_APPIMAGE_SIGIL:
            return self._network.wine_appimage_upstream_url("continuous-staging")
        elif self.wine_binary == constants.UNTESTED_WINE_DEVELOPMENT_APPIMAGE_SIGIL:
            return self._network.wine_appimage_upstream_url("continuous-devel")
        elif self.wine_binary == constants.RECOMMENDED_WINE_TARBALL_SIGIL:
            return self._network.wine_tarball_recommended_url()
        else:
            # self.wine_binary == constants.RECOMMENDED_WINE_APPIMAGE_SIGIL
            return self._network.wine_appimage_recommended_url()
        
    
    @property
    def wine_download_file_name(self) -> str:
        """Returns the file name of the recommended appimage with extension"""
        return os.path.basename(self.wine_download_url)

    @property
    def wine_recommended_version(self) -> str:
        # Getting version and branch rely on the filename having this format:
        #   wine-[branch]_[version]-[arch]
        return self.wine_download_file_name.split('-')[1].split('_')[1]

    @property
    def wine_dll_overrides(self) -> str:
        """Used to set WINEDLLOVERRIDES"""
        if self._overrides.wine_dll_overrides is not None:
            return self._overrides.wine_dll_overrides
        # Default is no overrides
        return ''

    @property
    def wine_debug(self) -> str:
        """Used to set WINEDEBUG"""
        if self._overrides.wine_debug is not None:
            return self._overrides.wine_debug
        return constants.DEFAULT_WINEDEBUG

    @property
    def wine_output_encoding(self) -> Optional[str]:
        """Attempt to guess the encoding of the wine output"""
        if self._overrides.wine_output_encoding is not None:
            return self._overrides.wine_output_encoding
        if self._wine_output_encoding is None:
            self._wine_output_encoding = wine.get_winecmd_encoding(self.app)
        return self._wine_output_encoding

    @property
    def app_wine_log_path(self) -> str:
        if self._overrides.app_wine_log_path is not None:
            return self._overrides.app_wine_log_path
        return constants.DEFAULT_APP_WINE_LOG_PATH

    @property
    def app_wine_log_previous_path(self) -> str:
        wine_log = Path(self.app_wine_log_path)
        return str(wine_log.with_suffix(".1" + wine_log.suffix))

    @property
    def app_log_path(self) -> str:
        if self._overrides.app_log_path is not None:
            return self._overrides.app_log_path
        return constants.DEFAULT_APP_LOG_PATH

    def toggle_faithlife_product_release_channel(self):
        if self._raw.faithlife_product_release_channel == "stable":
            new_channel = "beta"
        else:
            new_channel = "stable"
        self._raw.faithlife_product_release_channel = new_channel
        self._write()
    
    def toggle_installer_release_channel(self):
        if self._raw.app_release_channel == "stable":
            new_channel = "dev"
        else:
            new_channel = "stable"
        self._raw.app_release_channel = new_channel
        self._write()
    
    @property
    def backup_dir(self) -> Path:
        question = "New or existing folder to store backups in: "
        options = [PROMPT_OPTION_DIRECTORY]
        return Path(self._ask_if_not_found("backup_dir", question, options))
    
    @property
    def curses_color_scheme(self) -> str:
        """Color for the curses dialog
        
        returns one of: System, Logos, Light or Dark"""
        return self._raw.curses_color_scheme or 'Logos'

    @curses_color_scheme.setter
    def curses_color_scheme(self, value: Optional[str]):
        if value is not None and value not in self._curses_color_scheme_valid_values:
            raise ValueError(
                "Invalid curses theme, expected one of: "
                f"{", ".join(self._curses_color_scheme_valid_values)} but got: {value}"
            )
        self._raw.curses_color_scheme = value
        self._write()
    
    def cycle_curses_color_scheme(self):
        new_index = self._curses_color_scheme_valid_values.index(self.curses_color_scheme) + 1
        if new_index == len(self._curses_color_scheme_valid_values):
            new_index = 0
        self.curses_color_scheme = self._curses_color_scheme_valid_values[new_index]

    @property
    def logos_exe(self) -> Optional[str]:
        if (
            # Ensure we have all the context we need before attempting
            self._raw.faithlife_product is not None
            and self._raw.install_dir is not None
            and self._logos_appdata_dir is not None
        ):
            return f"{self._logos_appdata_dir}/{self._raw.faithlife_product}.exe"
        return None

    @property
    def wine_user(self) -> Optional[str]:
        # We don't want to prompt the user for install_dir if it isn't set
        # or anything that is used in the default install dir
        if (
            not self._raw.install_dir
            or not self._raw.faithlife_product 
            or not self._raw.faithlife_product_version
        ):
            return None
        # Cache a successful result (as it goes out to the fs)
        if not self._wine_user:
            self._wine_user = get_wine_user(self.wine_prefix)
        return self._wine_user

    @property
    def logos_cef_exe(self) -> Optional[str]:
        if self.wine_user is not None:
            # This name is the same even in Verbum
            return f'C:\\users\\{self.wine_user}\\AppData\\Local\\{self.faithlife_product}\\System\\LogosCEF.exe'
        return None

    @property
    def logos_indexer_exe(self) -> Optional[str]:
        if self.wine_user is not None:
            return (f'C:\\users\\{self.wine_user}\\AppData\\Local\\{self.faithlife_product}\\System\\'
                    f'{self.faithlife_product}Indexer.exe')
        return None

    @property
    def logos_login_exe(self) -> Optional[str]:
        if self.wine_user is not None:
            return (f'C:\\users\\{self.wine_user}\\AppData\\Local\\{self.faithlife_product}\\System\\'
                    f'{self.faithlife_product}.exe')
        return None

    @property
    def log_level(self) -> str | int:
        if self._overrides.log_level is not None:
            return self._overrides.log_level
        return constants.DEFAULT_LOG_LEVEL

    @property
    def skip_install_system_dependencies(self) -> bool:
        return bool(self._overrides.install_dependencies_skip)

    @skip_install_system_dependencies.setter
    def skip_install_system_dependencies(self, val: bool):
        self._overrides.install_dependencies_skip = val

    @property
    def download_dir(self) -> str:
        if self._download_dir is None:
            self._download_dir = constants.CACHE_DIR
        return self._download_dir
    
    @property
    def user_download_dir(self) -> str:
        if self._user_download_dir is None:
            self._user_download_dir = utils.get_user_downloads_dir()
        return self._user_download_dir

    @property
    def installed_faithlife_product_release(self) -> Optional[str]:
        if self._raw.install_dir is None:
            return None
        if self._installed_faithlife_product_release is None:
            self._installed_faithlife_product_release = utils.get_current_logos_version(self._logos_appdata_dir)
        return self._installed_faithlife_product_release

    @property
    def app_latest_version_url(self) -> str:
        return self._network.app_latest_version(self.app_release_channel).download_url

    @property
    def app_latest_version(self) -> str:
        return self._network.app_latest_version(self.app_release_channel).version

    @property
    def icu_latest_version(self) -> str:
        return self._network.icu_latest_version().version

    @property
    def icu_latest_version_url(self) -> str:
        return self._network.icu_latest_version().download_url
