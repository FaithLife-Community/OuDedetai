#!/usr/bin/env python3
import logging.handlers
from typing import Callable, Tuple

from ou_dedetai.app import UserExitedFromAsk
from ou_dedetai.cli_parser import parse_args
from ou_dedetai.config import (
    EphemeralConfiguration, PersistentConfiguration, get_wine_prefix_path
)

import logging
import os
import sys

from .repair import detect_and_recover

from . import cli_parser
from . import constants
from . import msg
from . import system
from . import utils


def setup_config() -> Tuple[EphemeralConfiguration, Callable[[EphemeralConfiguration], None]]:
    parser = cli_parser.get_parser()
    args = parser.parse_args()

    # Get config based on env and configuration file temporarily just to load a couple 
    # values out. We'll load this fully later.
    temp = EphemeralConfiguration.load()
    log_level = temp.log_level or constants.DEFAULT_LOG_LEVEL
    app_log_path = temp.app_log_path or constants.DEFAULT_APP_LOG_PATH
    del temp

    # Set runtime config.
    # Update log configuration.
    msg.update_log_level(log_level)
    msg.update_log_path(app_log_path)
    # test = logging.getLogger().handlers

    # Parse CLI args and update affected config vars.
    return parse_args(logging, args, parser)


def is_app_installed(ephemeral_config: EphemeralConfiguration):
    persistent_config = PersistentConfiguration.load_from_path(ephemeral_config.config_path) 
    if persistent_config.faithlife_product is None or persistent_config.install_dir is None: 
        # Not enough information stored to find the product
        return False
    wine_prefix = ephemeral_config.wine_prefix or get_wine_prefix_path(str(persistent_config.install_dir)) 
    return utils.find_installed_product(persistent_config.faithlife_product, wine_prefix) 


def run(ephemeral_config: EphemeralConfiguration, action: Callable[[EphemeralConfiguration], None]): 
    # Attempt to repair installation if it is broken.
    # Must be done before calling the action to avoid errosly thinking the app isn't
    # installed when it's broken
    detect_and_recover(ephemeral_config)
    # Run desired action (requested function, defaults to control_panel)
    if action == "disabled":
        print("That option is disabled.", file=sys.stderr)
        sys.exit(1)
    if action.__name__ == "database_operation":
        action(ephemeral_config)
        return
    if action.__name__ == 'run_control_panel':
        # if utils.app_is_installed():
        #     wine.set_logos_paths()
        action(ephemeral_config)  # run control_panel right away
        return
    
    # Proceeding with the CLI interface

    install_required = [
        'backup',
        'create_shortcuts',
        'install_icu',
        'remove_index_files',
        'remove_library_catalog',
        'restore',
        'run_indexing',
        'run_installed_app',
        'update_installed_app',
        'stop_installed_app',
        'set_appimage',
        'toggle_app_logging',
    ]
    if action.__name__ not in install_required:
        logging.info(f"Running function: {action.__name__}")
        action(ephemeral_config)
    elif is_app_installed(ephemeral_config):  # install_required; checking for app
        # wine.set_logos_paths()
        # Run the desired Logos action.
        logging.info(f"Running function: {action.__name__}")
        action(ephemeral_config)
    else:  # install_required, but app not installed
        print("App is not installed, but required for this operation. Consider installing first.", file=sys.stderr) 
        sys.exit(1)


def main():
    msg.initialize_logging()
    ephemeral_config, action = setup_config()
    system.check_architecture()

    # NOTE: DELETE_LOG is an outlier here. It's an action, but it's one that
    # can be run in conjunction with other actions, so it gets special
    # treatment here once config is set.
    app_log_path = ephemeral_config.app_log_path or constants.DEFAULT_APP_LOG_PATH
    if ephemeral_config.delete_log and os.path.isfile(app_log_path):
        # Write empty file.
        with open(app_log_path, 'w') as f:
            f.write('')

    # Run safety checks.
    # FIXME: Fix utils.die_if_running() for GUI; as it is, it breaks GUI
    # self-update when updating LLI as it asks for a confirmation in the CLI.
    # Disabled until it can be fixed. Avoid running multiple instances of the
    # program.
    # utils.die_if_running()
    if os.getuid() == 0 and not ephemeral_config.app_run_as_root_permitted:
        print("Running Wine/winetricks as root is highly discouraged. Use -f|--force-root if you must run as root. "
              "See https://wiki.winehq.org/FAQ#Should_I_run_Wine_as_root.3F", file=sys.stderr)
        sys.exit(1)

    # Print terminal banner
    logging.info(f"{constants.APP_NAME}, {constants.LLI_CURRENT_VERSION} by {constants.LLI_AUTHOR}.")

    try:
        run(ephemeral_config, action)
    except UserExitedFromAsk:
        # This isn't a critical failure, the user doesn't need a traceback,
        # they are the ones who told us to exit.
        pass


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
