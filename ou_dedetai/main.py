#!/usr/bin/env python3
import argparse
import asyncio
import threading
import time
from typing import Optional, Tuple

from ou_dedetai.app import App, UserExitedFromAsk
from ou_dedetai.config import (
    EphemeralConfiguration, PersistentConfiguration, get_wine_prefix_path
)
from ou_dedetai.dbus import main as dbus_main

import logging
import os
import sys

from .repair import detect_and_recover

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
    # FIXME: remove this deprecated option.
    # If we remove this today, scripts using -P will fail, as now it's an "unknown option"
    cfg.add_argument(
        '-P', '--passive', action='store_true',
        help='Legacy argument that used to specify to run the product installer non-interactively. '
        'Now this is the default. '
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
        help='backup current data',
    )
    cmd.add_argument(
        '--restore', action='store_true',
        help='restore data from backup',
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
        '--uninstall', action='store_true',
        help='Completely delete the faithlife software from your system',
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
        '--get-support', action='store_true',
        help='Generates a support bundle and prints out where to go for support',
    )
    cmd.add_argument(
        '--wine', nargs="+",
        help=(
            'run wine command'
            '; WARNING: wine will not accept user input!'
        ),
    )
    cmd.add_argument(
        '--winetricks', nargs='*',
        help="run winetricks command",
    )
    return parser


def parse_args(args, parser) -> Tuple[EphemeralConfiguration, App]: 
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
            message = f"Custom binary path does not exist: \"{args.custom_binary_path}\"\n"
            parser.exit(status=1, message=message)

    if args.assume_yes and not args.i_agree_to_faithlife_terms:
        message = ("Non-interactive installations MUST also agree to the EULA https://faithlife.com/terms "
                   "via the flag --i-agree-to-faithlife-terms\n")
        parser.exit(status=1, message=message)

    if args.assume_yes:
        ephemeral_config.assume_yes = True

    if args.i_agree_to_faithlife_terms:
        ephemeral_config.agreed_to_faithlife_terms = True


    def cli_operation(action: str, config: EphemeralConfiguration) -> cli.CLI:
        """Wrapper for a function pointer to a given function under CLI"""
        app = cli.CLI(config)
        output = getattr(app, action)
        app.post_run_action = output
        return app

    # Set action return function.
    actions = [
        'backup',
        'create_shortcuts',
        'edit_config',
        'install_dependencies',
        'install_icu',
        'remove_index_files',
        'uninstall',
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
        'winetricks',
        "get_support"
    ]

    app: Optional[App] = None
    for arg in actions:
        if getattr(args, arg) or getattr(args, arg) == []:
            if arg == "set_appimage":
                ephemeral_config.wine_appimage_path = getattr(args, arg)[0]
                if not utils.file_exists(ephemeral_config.wine_appimage_path):
                    e = f"Invalid file path: '{ephemeral_config.wine_appimage_path}'. File does not exist."
                    raise argparse.ArgumentTypeError(e)
                if not utils.check_appimage(ephemeral_config.wine_appimage_path):
                    e = f"{ephemeral_config.wine_appimage_path} is not an AppImage."
                    raise argparse.ArgumentTypeError(e)
            # Re-use this variable for either wine or winetricks execution
            elif arg == 'wine' or arg == 'winetricks':
                ephemeral_config.wine_args = getattr(args, arg)
            app = cli_operation(arg, ephemeral_config)
            break
    if getattr(args, "install_app"):
        app = install_app(ephemeral_config)
    if app is None:
        app = initialize_control_panel_app(ephemeral_config)

    logging.debug(f"App will run the following when it's ready: {app.post_run_action=}")
    return ephemeral_config, app


def initialize_control_panel_app(ephemeral_config: EphemeralConfiguration) -> App:
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        return gui_app.ControlWindowGuiApp(ephemeral_config)
    else:
        # CLI doesn't have a control panel, and we've already parsed the cli args.
        # When args are lacking, use the TUI
        return tui_app.TUI(ephemeral_config)

def install_app(ephemeral_config: EphemeralConfiguration) -> App:
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        return gui_app.InstallerGuiApp(ephemeral_config)
    else:
        # No need to handle the TUI menu-ing, terminal users can see the output raw.
        app = cli.CLI(ephemeral_config)
        app.post_run_action = app.install_app
        return app


def setup_config() -> Tuple[EphemeralConfiguration, App]: 
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
    persistent_config = PersistentConfiguration.load_from_path(ephemeral_config.config_path) 
    if persistent_config.faithlife_product is None or persistent_config.install_dir is None: 
        # Not enough information stored to find the product
        return False
    wine_prefix = ephemeral_config.wine_prefix or get_wine_prefix_path(str(persistent_config.install_dir)) 
    return utils.find_installed_product(persistent_config.faithlife_product, wine_prefix) 

async def async_main(app: App):
    started = time.time()
    # Give the app 20 seconds to start
    while not app.is_running and time.time() - started < 5:
        # Sleep only a tiny bit of time as we need to catch the app while it's running.
        await asyncio.sleep(.1)
    if not app.is_running:
        logging.debug("Never saw the app start, refusing to launch dbus daemon")
        return
    # Then start dbus' main
    await dbus_main(app)
    # Then wait for app to stop
    while app.is_running:
        await asyncio.sleep(1)

def main():
    msg.initialize_logging()
    ephemeral_config, app = setup_config()
    system.check_architecture()

    # Start dbus listening
    # Spawn an asyncio worker thread in the background
    #
    # Example code for how to spawn async functions using this worker (where main is an async function):
    # asyncio.run_coroutine_threadsafe(main(), asyncio.get_event_loop())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio_worker_thread = threading.Thread(target=loop.run_until_complete, name="Asyncio Event Loop", args=[async_main(app)])
    asyncio_worker_thread.start()

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
        # Attempt to repair installation if it is broken.
        # Must be done before calling the action to avoid erroneously thinking the app isn't
        # installed when it's broken
        detect_and_recover(ephemeral_config)

        # Start App's main thread (which is expected to block)
        app.start()
    except UserExitedFromAsk:
        # This isn't a critical failure, the user doesn't need a traceback,
        # they are the ones who told us to exit.
        pass

    # Cleanup
    app.is_running=False
    app.exit(reason=None, intended=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
