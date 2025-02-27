#!/usr/bin/env python3
import argparse
import curses
import logging.handlers
from typing import Callable, Tuple

from ou_dedetai.config import (
    EphemeralConfiguration, PersistentConfiguration, get_wine_prefix_path
)

import logging
import os
import sys

from ou_dedetai.repair import detect_and_recover

from . import cli
from . import constants
from . import gui_app
from . import msg
from . import system
from . import tui_app
from . import utils


def get_parser():
    desc = "Installs FaithLife Bible Software with Wine."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        '-v', '--version', action='version',
        version=(
            f"{constants.APP_NAME}, "
            f"{constants.LLI_CURRENT_VERSION} by {constants.LLI_AUTHOR}"
        ),
    )

    # Define options that affect runtime config.
    cfg = parser.add_argument_group(title="runtime config options")
    cfg.add_argument(
        '-a', '--check-for-updates', action='store_true',
        help='force a check for updates'
    )
    cfg.add_argument(
        '-K', '--skip-dependencies', action='store_true',
        help='skip dependencies check and installation',
    )
    cfg.add_argument(
        '-V', '--verbose', action='store_true',
        help='enable verbose mode',
    )
    cfg.add_argument(
        '-D', '--debug', action='store_true',
        help='enable Wine debug output',
    )
    cfg.add_argument(
        '-c', '--config', metavar='CONFIG_FILE',
        help=(
            "use a custom config file during installation "
            f"[default: {constants.DEFAULT_CONFIG_PATH}]"
        ),
    )
    cfg.add_argument(
        '-f', '--force-root', action='store_true',
        help=(
            "Running Wine as root is highly discouraged. "
            "Set this to do allow it anyways"
        ),
    )
    cfg.add_argument(
        '-p', '--custom-binary-path', metavar='CUSTOMBINPATH',
        help='specify a custom wine binary path',
    )
    cfg.add_argument(
        '-L', '--delete-log', action='store_true',
        help='delete the log file',
    )
    cfg.add_argument(
        '-P', '--passive', action='store_true',
        help='run product installer non-interactively. '
        'Consider agreeing to the terms as well --i-agree-to-faithlife-terms',
    )
    cfg.add_argument(
        '-y', '--assume-yes', action='store_true',
        help='Assumes yes (or default) to all prompts. '
        'Useful for entirely non-interactive installs. '
        'Consider agreeing to the terms as well --i-agree-to-faithlife-terms',
    )
    cfg.add_argument(
        '--i-agree-to-faithlife-terms', action='store_true',
        help='By passing this flag you agree to https://faithlife.com/terms',
    )
    cfg.add_argument(
        '-q', '--quiet', action='store_true',
        help='Suppress all non-error output',
    )

    # Define runtime actions (mutually exclusive).
    grp = parser.add_argument_group(
        title="subcommands",
        description=(
            "these options run specific subcommands; "
            "only 1 at a time is accepted"
        ),
    )
    cmd = grp.add_mutually_exclusive_group()
    cmd.add_argument(
        '--install-app', action='store_true',
        help='install FaithLife app',
    )
    cmd.add_argument(
        '--run-installed-app', '-C', action='store_true',
        help='run installed FaithLife app',
    )
    cmd.add_argument(
        '--stop-installed-app', action='store_true',
        help='stop the installed FaithLife app if running',
    )
    cmd.add_argument(
        '--run-indexing', action='store_true',
        help='perform indexing',
    )
    cmd.add_argument(
        '--remove-library-catalog', action='store_true',
        # help='remove library catalog database file'
        help=argparse.SUPPRESS,
    )
    cmd.add_argument(
        '--remove-index-files', action='store_true',
        help=argparse.SUPPRESS,
    )
    cmd.add_argument(
        '--edit-config', action='store_true',
        help='edit configuration file',
    )
    cmd.add_argument(
        '--install-dependencies', '-I', action='store_true',
        help="install your distro's dependencies",
    )
    cmd.add_argument(
        '--backup', action='store_true',
        # help='perform backup',
        help=argparse.SUPPRESS,
    )
    cmd.add_argument(
        '--restore', action='store_true',
        # help='perform restore',
        help=argparse.SUPPRESS,
    )
    cmd.add_argument(
        '--update-self', '-u', action='store_true',
        help=f'Update {constants.APP_NAME} to the latest release.',
    )
    cmd.add_argument(
        '--update-latest-appimage', '-U', action='store_true',
        help='Update the to the latest AppImage.',
    )
    cmd.add_argument(
        '--set-appimage', nargs=1, metavar=('APPIMAGE_FILE_PATH'),
        help='Update the AppImage symlink. Requires a path.',
    )
    cmd.add_argument(
        '--install-icu', action='store_true',
        help='Install ICU data files for Logos 30+',
    )
    cmd.add_argument(
        '--toggle-app-logging', action='store_true',
        help='enable/disable app logs',
    )
    cmd.add_argument(
        '--create-shortcuts', action='store_true',
        help='[re-]create app shortcuts',
    )
    cmd.add_argument(
        '--remove-install-dir', action='store_true',
        help='delete the current installation folder',
    )
    cmd.add_argument(
        '--dirlink', action='store_true',
        # help='create directory link',
        help=argparse.SUPPRESS,
    )
    cmd.add_argument(
        '--check-resources', action='store_true',
        # help='check resources'
        help=argparse.SUPPRESS,
    )
    cmd.add_argument(
        '--wine', nargs="+",
        help=(
            'run wine command'
            '; WARNING: wine will not accept user input!'
        ),
    )
    return parser


def parse_args(args, parser) -> Tuple[EphemeralConfiguration, Callable[[EphemeralConfiguration], None]]: #noqa: E501
    if args.config:
        ephemeral_config = EphemeralConfiguration.load_from_path(args.config)
    else:
        ephemeral_config = EphemeralConfiguration.load()

    if args.quiet:
        msg.update_log_level(logging.WARNING)
        ephemeral_config.quiet = True

    if args.verbose:
        msg.update_log_level(logging.INFO)

    if args.debug:
        msg.update_log_level(logging.DEBUG)
        if not ephemeral_config.wine_debug:
            ephemeral_config.wine_debug = constants.DEFAULT_WINEDEBUG
        # Developers may want to consider adding +relay for excessive debug output
        ephemeral_config.wine_debug+=',+loaddll,+pid,+threadname'

    if args.delete_log:
        ephemeral_config.delete_log = True

    if args.set_appimage:
        ephemeral_config.wine_appimage_path = args.set_appimage[0]

    # FIXME: Should this have been args.check_for_updates?
    # Should this even be an option?
    # if network.check_for_updates:
    #     ephemeral_config.check_updates_now = True

    if args.skip_dependencies or constants.RUNMODE == 'snap':
        ephemeral_config.install_dependencies_skip = True

    if args.force_root:
        ephemeral_config.app_run_as_root_permitted = True

    if args.custom_binary_path:
        if os.path.isdir(args.custom_binary_path):
            # Set legacy environment variable for config to pick up
            os.environ["CUSTOMBINPATH"] = args.custom_binary_path
        else:
            message = f"Custom binary path does not exist: \"{args.custom_binary_path}\"\n"  # noqa: E501
            parser.exit(status=1, message=message)

    if args.assume_yes and not args.i_agree_to_faithlife_terms:
        message = "Non-interactive installations MUST also agree to the EULA https://faithlife.com/terms via the flag --i-agree-to-faithlife-terms\n"  # noqa: E501
        parser.exit(status=1, message=message)

    if args.assume_yes:
        ephemeral_config.assume_yes = True

    if args.passive or args.assume_yes:
        ephemeral_config.faithlife_install_passive = True

    if args.i_agree_to_faithlife_terms:
        ephemeral_config.agreed_to_faithlife_terms = True


    def cli_operation(action: str) -> Callable[[EphemeralConfiguration], None]:
        """Wrapper for a function pointer to a given function under CLI
        
        Lazily instantiates CLI at call-time"""
        def _run(config: EphemeralConfiguration):
            getattr(cli.CLI(config), action)()
        output = _run
        output.__name__ = action
        return output

    # Set action return function.
    actions = [
        'backup',
        'create_shortcuts',
        'edit_config',
        'install_dependencies',
        'install_icu',
        'remove_index_files',
        'remove_install_dir',
        'remove_library_catalog',
        'restore',
        'run_indexing',
        'run_installed_app',
        'stop_installed_app',
        'set_appimage',
        'toggle_app_logging',
        'update_self',
        'update_latest_appimage',
        'wine',
    ]

    run_action = None
    for arg in actions:
        if getattr(args, arg):
            if arg == "set_appimage":
                ephemeral_config.wine_appimage_path = getattr(args, arg)[0]
                if not utils.file_exists(ephemeral_config.wine_appimage_path):
                    e = f"Invalid file path: '{ephemeral_config.wine_appimage_path}'. File does not exist."  # noqa: E501
                    raise argparse.ArgumentTypeError(e)
                if not utils.check_appimage(ephemeral_config.wine_appimage_path):
                    e = f"{ephemeral_config.wine_appimage_path} is not an AppImage."
                    raise argparse.ArgumentTypeError(e)
            elif arg == 'wine':
                ephemeral_config.wine_args = getattr(args, 'wine')
            run_action = cli_operation(arg)
            break
    if getattr(args, "install_app"):
        run_action = install_app
    if run_action is None:
        run_action = run_control_panel
    logging.debug(f"{run_action=}")
    return ephemeral_config, run_action


def run_control_panel(ephemeral_config: EphemeralConfiguration):
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        gui_app.start_gui_app(ephemeral_config)
    else:
        try:
            curses.wrapper(tui_app.control_panel_app, ephemeral_config)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            logging.info("Caught SystemExit, exiting gracefully…")
            raise
        except curses.error as e:
            logging.error(f"Curses error in run_control_panel(): {e}")
            raise e
        except Exception as e:
            logging.error(f"An error occurred in run_control_panel(): {e}")
            raise e

def install_app(ephemeral_config: EphemeralConfiguration):
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        gui_app.start_gui_app(ephemeral_config, install_only=True)
    else:
        cli.CLI(ephemeral_config).install_app()


def setup_config() -> Tuple[EphemeralConfiguration, Callable[[EphemeralConfiguration], None]]: #noqa: E501
    parser = get_parser()
    cli_args = parser.parse_args()  # parsing early lets 'help' run immediately

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
    return parse_args(cli_args, parser)


def is_app_installed(ephemeral_config: EphemeralConfiguration):
    persistent_config = PersistentConfiguration.load_from_path(ephemeral_config.config_path) #noqa: E501
    if persistent_config.faithlife_product is None or persistent_config.install_dir is None: #noqa: E501
        # Not enough information stored to find the product
        return False
    wine_prefix = ephemeral_config.wine_prefix or get_wine_prefix_path(str(persistent_config.install_dir)) #noqa: E501
    return utils.find_installed_product(persistent_config.faithlife_product, wine_prefix) #noqa: E501


def run(ephemeral_config: EphemeralConfiguration, action: Callable[[EphemeralConfiguration], None]): #noqa: E501
    # Attempt to repair installation if it is broken.
    # Must be done before calling the action to avoid errosly thinking the app isn't
    # installed when it's broken
    detect_and_recover(ephemeral_config)
    # Run desired action (requested function, defaults to control_panel)
    if action == "disabled":
        print("That option is disabled.", file=sys.stderr)
        sys.exit(1)
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
        logging.info(f"Running function: {action.__name__}")  # noqa: E501
        action(ephemeral_config)
    else:  # install_required, but app not installed
        print("App is not installed, but required for this operation. Consider installing first.", file=sys.stderr) #noqa: E501
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
        print("Running Wine as root is highly discouraged. Use -f|--force-root if you must run as root. See https://wiki.winehq.org/FAQ#Should_I_run_Wine_as_root.3F", file=sys.stderr)  # noqa: E501
        sys.exit(1)

    # Print terminal banner
    logging.info(f"{constants.APP_NAME}, {constants.LLI_CURRENT_VERSION} by {constants.LLI_AUTHOR}.")  # noqa: E501

    run(ephemeral_config, action)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
