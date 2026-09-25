import argparse
import os
from typing import Tuple, Callable

from . import constants, cli_parser_database, msg, cli, utils, actions
from .config import EphemeralConfiguration


def get_parser():
    desc = "Installs FaithLife Bible Software with Wine."

    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument(
        '-v', '--version',
        action='version',
        version=(
            f"{constants.APP_NAME}, "
            f"{constants.LLI_CURRENT_VERSION} by {constants.LLI_AUTHOR}"
        ),
    )


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
        '--update-installed-app', action='store_true',
        help='update the installed FaithLife app to the latest release',
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

    cli_parser_database.add_database_parser(
        parser.add_subparsers(
            dest="command",
            title="commands",
        )
    )

    return parser


def parse_args(logging, args, parser) -> Tuple[EphemeralConfiguration, Callable[[EphemeralConfiguration], None]]:
    if args.config:
        ephemeral_config = EphemeralConfiguration.load_from_path(args.config)
    else:
        ephemeral_config = EphemeralConfiguration.load()

    if args.command == "database":
        return (
            ephemeral_config,
            cli_parser_database.parse_database_command(args, ephemeral_config)
        )

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


    def cli_operation(action: str) -> EphemeralConfiguration:
        """Wrapper for a function pointer to a given function under CLI

        Lazily instantiates CLI at call-time"""
        def _run(config: EphemeralConfiguration):
            getattr(cli.CLI(config), action)()
        output = _run
        output.__name__ = action
        return output

    # Set action return function.
    action_names = [
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
        'update_installed_app',
        'stop_installed_app',
        'set_appimage',
        'toggle_app_logging',
        'update_self',
        'update_latest_appimage',
        'wine',
        'winetricks',
        "get_support"
    ]

    run_action = None
    for arg in action_names:
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
            run_action = cli_operation(arg)
            break
    if args.install_app:
        run_action = actions.install_app

    if run_action is None:
        run_action = actions.run_control_panel

    return ephemeral_config, run_action
